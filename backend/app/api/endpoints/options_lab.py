"""
Option Lab endpoints.

Phase 1: GET /api/v1/options/gex/{ticker}
    Returns the dealer-gamma curve, gamma wall, put support, and
    total GEX for the requested underlying. Spot is sourced from
    Alpaca's latest 1-minute bar (15-min delayed on free tier);
    falls back to yfinance.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import polars as pl
import requests
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from ...models.options_schemas import (
    DCFSummaryModel,
    GEXCurvePoint,
    GEXResponse,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedContractModel,
    RiskFilterModel,
    StrategyROCModel,
)
from ...services.dcf import compute_dcf
from ...services.gex import compute_net_gex
from ...services.greeks import attach_greeks
from ...services.option_recommender import build_recommendation
from ...services.option_risk_filter import filter_option_risk
from ...services.options_data import load_options_chain


router = APIRouter(prefix="/api/v1/options", tags=["options"])

ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars/latest"
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"


# ── Spot price helper ─────────────────────────────────────────────────

def _spot_from_alpaca(ticker: str) -> float | None:
    """Latest available trade price (15-min delayed on free tier)."""
    api_key = (os.getenv("ALPACA_API_KEY_ID") or "").strip()
    api_secret = (os.getenv("ALPACA_API_SECRET_KEY") or "").strip()
    if not api_key or not api_secret:
        return None
    try:
        resp = requests.get(
            ALPACA_BARS_URL,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            params={"symbols": ticker, "feed": "iex"},
            timeout=10,
        )
        resp.raise_for_status()
        bars = resp.json().get("bars") or {}
        bar = bars.get(ticker)
        if bar and bar.get("c"):
            return float(bar["c"])
    except requests.RequestException as exc:
        logger.warning(f"Alpaca latest-bar fetch failed for {ticker}: {exc}")
    return None


def _spot_from_yfinance(ticker: str) -> float | None:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "last_price", None) or info.get("lastPrice")
        return float(price) if price else None
    except Exception as exc:
        logger.warning(f"yfinance spot fetch failed for {ticker}: {exc}")
        return None


def _resolve_spot(ticker: str) -> float:
    spot = _spot_from_alpaca(ticker) or _spot_from_yfinance(ticker)
    if spot is None or spot <= 0:
        raise HTTPException(
            status_code=503,
            detail=f"Could not resolve spot price for {ticker}",
        )
    return spot


# ── Earnings date ─────────────────────────────────────────────────────

def _next_earnings_date(ticker: str) -> date | None:
    """Pull the next upcoming earnings release from FMP (best-effort)."""
    api_key = (os.getenv("FMP_API_KEY") or "").strip("'\" ")
    if not api_key:
        return None
    try:
        today = date.today()
        resp = requests.get(
            f"{FMP_STABLE_BASE}/earnings-calendar",
            params={
                "symbol": ticker,
                "from": today.isoformat(),
                "to": (today + timedelta(days=120)).isoformat(),
                "apikey": api_key,
            },
            timeout=10,
        )
        if resp.status_code in (401, 402, 403):
            return None
        resp.raise_for_status()
        events = resp.json() or []
    except requests.RequestException as exc:
        logger.warning(f"FMP earnings fetch failed for {ticker}: {exc}")
        return None

    if not isinstance(events, list):
        return None
    future_dates: list[date] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        d = ev.get("date") or ev.get("fiscalDateEnding")
        if not d:
            continue
        try:
            parsed = date.fromisoformat(str(d)[:10])
        except ValueError:
            continue
        if parsed >= today:
            future_dates.append(parsed)
    return min(future_dates) if future_dates else None


# ── Shared chain prep for recommendation pipeline ────────────────────

def _prep_chain_for_strategy(
    ticker: str,
    spot: float,
    today: date,
    *,
    max_days_to_expiry: int = 60,
    strike_window_pct: float = 0.25,
):
    chain = load_options_chain(ticker)
    if chain is None or chain.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"No options chain available for {ticker}",
        )

    expiry_cutoff = today + timedelta(days=max_days_to_expiry)
    strike_low = spot * (1.0 - strike_window_pct)
    strike_high = spot * (1.0 + strike_window_pct)

    filtered = chain.filter(
        (pl.col("expiry") >= today)
        & (pl.col("expiry") <= expiry_cutoff)
        & (pl.col("strike") >= strike_low)
        & (pl.col("strike") <= strike_high)
    )
    if filtered.is_empty():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No contracts for {ticker} within ±{int(strike_window_pct * 100)}% "
                f"of ${spot:.2f} in the next {max_days_to_expiry} days"
            ),
        )
    return filtered


# ── Endpoint ──────────────────────────────────────────────────────────

@router.get("/gex/{ticker}", response_model=GEXResponse)
def get_gex(
    ticker: str,
    max_days_to_expiry: int = Query(
        60,
        ge=1,
        le=365,
        description="Only aggregate contracts expiring within this many days",
    ),
    strike_window_pct: float = Query(
        0.25,
        ge=0.05,
        le=1.0,
        description="Restrict aggregation to strikes within ±this fraction of spot",
    ),
):
    """Build the dealer-gamma curve for ``ticker``.

    The curve is bucketed by strike. Strikes outside ``strike_window_pct``
    of spot are dropped (their open interest is small but the noise
    can dwarf the wall). Contracts expiring beyond
    ``max_days_to_expiry`` are also dropped, because longer-dated
    gamma is too small to drive near-term hedging flow.
    """
    ticker = ticker.upper()
    chain = load_options_chain(ticker)
    if chain is None or chain.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"No options chain available for {ticker}",
        )

    spot = _resolve_spot(ticker)
    today = date.today()
    expiry_cutoff = today + timedelta(days=max_days_to_expiry)
    strike_low = spot * (1.0 - strike_window_pct)
    strike_high = spot * (1.0 + strike_window_pct)

    filtered = chain.filter(
        (pl.col("expiry") >= today)
        & (pl.col("expiry") <= expiry_cutoff)
        & (pl.col("strike") >= strike_low)
        & (pl.col("strike") <= strike_high)
        & (pl.col("oi") > 0)
    )

    if filtered.is_empty():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No contracts for {ticker} within ±{int(strike_window_pct * 100)}% "
                f"of ${spot:.2f} expiring in the next {max_days_to_expiry} days"
            ),
        )

    needs_greeks = (
        "gamma" not in filtered.columns
        or filtered["gamma"].null_count() == filtered.height
        or filtered["gamma"].fill_null(0).abs().sum() == 0
    )
    if needs_greeks:
        if filtered["iv"].null_count() == filtered.height:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Options chain for {ticker} has no IV — cannot compute "
                    "Greeks fallback"
                ),
            )
        filtered = attach_greeks(filtered, spot=spot, as_of=today)

    result = compute_net_gex(filtered, spot=spot)

    # If Greeks were populated upstream, the chain came from Alpaca (yfinance
    # never returns Greeks). We use this as a coarse source attribution.
    source = "yfinance" if needs_greeks else "alpaca"

    return GEXResponse(
        ticker=ticker,
        spot=spot,
        as_of=datetime.now(tz=timezone.utc),
        contracts_loaded=int(filtered.height),
        expiry_filter=expiry_cutoff,
        curve=[GEXCurvePoint(**p) for p in result.curve],
        gamma_wall=result.gamma_wall,
        support_wall=result.support_wall,
        put_support=result.put_support,
        total_gex=result.total_gex,
        source=source,
    )


# ── Phase 2: full Sell-Put recommendation ─────────────────────────────

@router.post("/recommend/{ticker}", response_model=RecommendationResponse)
def recommend(
    ticker: str,
    body: RecommendationRequest | None = None,
):
    """Compose a full Sell-Put recommendation.

    Pipeline: chain → GEX wall → DCF floor → strike/expiry pick →
    ROC computation → optional LLM grounding for risk flags.
    """
    body = body or RecommendationRequest()
    ticker = ticker.upper()
    today = date.today()

    spot = _resolve_spot(ticker)
    chain = _prep_chain_for_strategy(
        ticker=ticker,
        spot=spot,
        today=today,
        max_days_to_expiry=90,
        strike_window_pct=0.25,
    )

    # Greeks fallback when the upstream provider didn't include them.
    needs_greeks = (
        "gamma" not in chain.columns
        or chain["gamma"].null_count() == chain.height
        or chain["gamma"].fill_null(0).abs().sum() == 0
    )
    if needs_greeks:
        if chain["iv"].null_count() == chain.height:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Options chain for {ticker} has no IV — cannot compute "
                    "Greeks fallback"
                ),
            )
        chain = attach_greeks(chain, spot=spot, as_of=today, risk_free_rate=body.risk_free_rate)

    # GEX from contracts with non-zero OI only.
    gex_input = chain.filter(pl.col("oi") > 0)
    gex_result = (
        compute_net_gex(gex_input, spot=spot)
        if not gex_input.is_empty()
        else None
    )
    gamma_wall = gex_result.gamma_wall if gex_result else None
    support_wall = gex_result.support_wall if gex_result else None

    # DCF
    dcf = compute_dcf(ticker, wacc=body.wacc)

    # Earnings calendar (best-effort)
    earnings_date = _next_earnings_date(ticker)

    rec = build_recommendation(
        ticker=ticker,
        spot=spot,
        chain=chain,
        gamma_wall=gamma_wall,
        support_wall=support_wall,
        valuation_floor=dcf.fair_value_per_share,
        earnings_date=earnings_date,
        today=today,
        aggressiveness=body.aggressiveness,
    )

    if rec.contract is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not build a Sell-Put recommendation for {ticker}: {rec.rationale}",
        )

    # LLM risk filter
    if body.enable_llm_filter:
        risk = filter_option_risk(
            ticker=ticker,
            spot=spot,
            gamma_wall=gamma_wall,
            valuation_floor=dcf.fair_value_per_share,
            proposed_strike=rec.contract.strike,
            proposed_expiration=rec.contract.expiration,
            iv_rank=rec.contract.iv_rank,
        )
    else:
        risk = {
            "risk_flags": [],
            "confidence_score": None,
            "rationale": "LLM filter disabled by request.",
            "sources_consulted": [],
        }

    # Pick the requested margin mode for ROC
    if body.margin_mode == "cash_secured":
        roc_cs_out = rec.roc_cash_secured
        roc_rt_out = None
    elif body.margin_mode == "reg_t":
        roc_cs_out = None
        roc_rt_out = rec.roc_reg_t
    else:
        roc_cs_out = rec.roc_cash_secured
        roc_rt_out = rec.roc_reg_t

    return RecommendationResponse(
        ticker=ticker,
        action="SELL_PUT",
        spot=spot,
        as_of=datetime.now(tz=timezone.utc),
        strike_pick_method=rec.strike_pick_method,
        valuation_floor=rec.valuation_floor,
        gamma_wall=rec.gamma_wall,
        support_wall=rec.support_wall,
        sigma_buffer=rec.sigma_buffer,
        final_strike=rec.final_strike,
        rationale=rec.rationale,
        contract=RecommendedContractModel(**vars(rec.contract)) if rec.contract else None,
        roc_cash_secured=StrategyROCModel(**vars(roc_cs_out)) if roc_cs_out else None,
        roc_reg_t=StrategyROCModel(**vars(roc_rt_out)) if roc_rt_out else None,
        dcf=DCFSummaryModel(
            method=dcf.method,
            fair_value_per_share=dcf.fair_value_per_share,
            fcf_baseline=dcf.fcf_baseline,
            growth_rate_used=dcf.growth_rate_used,
            terminal_growth=dcf.terminal_growth,
            wacc=dcf.wacc,
            horizon_years=dcf.horizon_years,
            notes=dcf.notes,
        ),
        risk_filter=RiskFilterModel(**risk),
    )
