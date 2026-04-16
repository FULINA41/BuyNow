"""
Fast inference API for the Global Panel Model.

Endpoint: GET /api/v1/predict/{ticker}?model=alphanet|lgbm

Flow:
    1. Fetch last MAX_LOOKBACK_DAYS of daily OHLCV from Alpaca.
    2. Compute technical features via the shared Polars feature engine.
    3. Slice the most recent SEQ_LEN-day window as the model input.
    4. Dispatch to ModelManager.predict() (AlphaNet or LightGBM).
    5. Return the signal dict.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import numpy as np
import polars as pl
import requests
from fastapi import APIRouter, HTTPException
from loguru import logger

from ...ml.features import FEATURE_COLS, calculate_features_polars
from ...ml.model import ModelManager

router = APIRouter(prefix="/api/v1", tags=["predict"])

MAX_LOOKBACK_DAYS = 180
SEQ_LEN = 20
ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"


# ── Data fetch ────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str, days: int = MAX_LOOKBACK_DAYS) -> pl.DataFrame:
    """Fetch recent daily OHLCV from Alpaca and return a Polars panel
    with columns [ticker, date, open, high, low, close, volume]."""
    api_key = (os.getenv("ALPACA_API_KEY_ID") or "").strip()
    api_secret = (os.getenv("ALPACA_API_SECRET_KEY") or "").strip()
    if not api_key or not api_secret:
        raise HTTPException(
            status_code=503, detail="Alpaca credentials not configured",
        )

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    end_dt = datetime.now(tz=timezone.utc) - timedelta(minutes=16)
    start_dt = end_dt - timedelta(days=days)

    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()

    params: dict = {
        "symbols": ticker,
        "timeframe": "1Day",
        "start": start_str,
        "end": end_str,
        "adjustment": "all",
        "limit": 10000,
        "feed": "sip",
        "sort": "asc",
    }

    all_bars: list[dict] = []
    page_token: str | None = None

    try:
        while True:
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                ALPACA_BARS_URL, headers=headers, params=params, timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            all_bars.extend((payload.get("bars") or {}).get(ticker, []))
            page_token = payload.get("next_page_token")
            if not page_token:
                break
    except requests.RequestException as exc:
        logger.error(f"Alpaca fetch failed for {ticker}: {exc}")
        raise HTTPException(
            status_code=503, detail=f"Market data unavailable: {exc}",
        )

    if not all_bars:
        raise HTTPException(
            status_code=404,
            detail=f"No market data returned for {ticker}",
        )

    rows = [
        {
            "ticker": ticker,
            "date": date.fromisoformat(bar["t"][:10]),
            "open": float(bar["o"]),
            "high": float(bar["h"]),
            "low": float(bar["l"]),
            "close": float(bar["c"]),
            "volume": int(bar["v"]),
        }
        for bar in all_bars
    ]

    return pl.DataFrame(
        rows,
        schema={
            "ticker": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
        },
    ).sort("date")


# ── Endpoint ──────────────────────────────────────────────────────────

@router.get("/predict/{ticker}")
def predict(
    ticker: str,
    model: Literal["alphanet", "lgbm"] = "lgbm",
):
    """Run ML inference for a single ticker.

    Returns predicted 5-day forward return (both models),
    plus direction probability and volatility estimate for AlphaNet.
    """
    ticker = ticker.upper()
    mgr = ModelManager()

    if model not in mgr.available_models:
        raise HTTPException(
            status_code=503,
            detail=f"Model '{model}' not loaded. Available: {mgr.available_models}",
        )

    # 1. Fetch OHLCV
    df = _fetch_ohlcv(ticker)

    # 2. Calculate features (same pipeline used during training)
    df = calculate_features_polars(df)
    df = df.drop_nulls(subset=FEATURE_COLS)

    if len(df) < SEQ_LEN:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only {len(df)} valid rows after feature calculation "
                f"(need at least {SEQ_LEN})"
            ),
        )

    # 3. Extract the most recent SEQ_LEN-day feature window
    window = df.tail(SEQ_LEN)
    features = window.select(FEATURE_COLS).to_numpy().astype(np.float32)

    # 4. Inference
    result = mgr.predict(name=model, ticker=ticker, temporal_features=features)

    # 5. Unwrap single-element lists for a cleaner response
    for key in ("pred_return", "pred_direction", "pred_volatility"):
        val = result.get(key)
        if isinstance(val, list) and len(val) == 1:
            result[key] = val[0]

    result["ticker"] = ticker
    result["seq_len"] = SEQ_LEN
    result["data_points"] = len(df)
    return result
