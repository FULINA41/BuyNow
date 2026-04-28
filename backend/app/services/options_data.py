"""
Options chain fetcher.

Primary source: Alpaca Market Data ``/v1beta1/options/snapshots/{symbol}``.
This endpoint is documented under the OPRA feed and returns latest
quote, latest trade, and the live Greeks/IV per contract for tickers
that the account is subscribed to. Free tiers may receive an empty
payload or 403 for this endpoint — in that case we fall back to
yfinance ``Ticker.option_chain()``.

Output schema (Polars DataFrame):

    symbol  : str   OCC contract symbol (e.g. "NVDA260516P00880000")
    type    : str   "call" | "put"
    strike  : f64
    expiry  : Date
    bid     : f64
    ask     : f64
    mid     : f64   (bid+ask)/2 when both present, else last/None
    last    : f64
    iv      : f64   implied volatility, decimal (0.30 = 30%)
    oi      : i64   open interest
    volume  : i64
    delta   : f64   nullable (filled by greeks.attach_greeks if missing)
    gamma   : f64   nullable
    theta   : f64   nullable
    vega    : f64   nullable

Cached per-ticker for 15 minutes (matches Alpaca free-tier delay).
"""
from __future__ import annotations

import os
import re
import time
from datetime import date, datetime
from functools import lru_cache

import polars as pl
import requests
from loguru import logger


ALPACA_OPTIONS_BASE = "https://data.alpaca.markets/v1beta1/options"

_OCC_PATTERN = re.compile(
    r"^(?P<root>[A-Z]+)"
    r"(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})"
    r"(?P<cp>[CP])"
    r"(?P<strike>\d{8})$"
)

_SCHEMA = {
    "symbol": pl.Utf8,
    "type": pl.Utf8,
    "strike": pl.Float64,
    "expiry": pl.Date,
    "bid": pl.Float64,
    "ask": pl.Float64,
    "mid": pl.Float64,
    "last": pl.Float64,
    "iv": pl.Float64,
    "oi": pl.Int64,
    "volume": pl.Int64,
    "delta": pl.Float64,
    "gamma": pl.Float64,
    "theta": pl.Float64,
    "vega": pl.Float64,
}


# ── OCC contract symbol parsing ───────────────────────────────────────

def parse_occ_symbol(occ: str) -> dict | None:
    """Extract (root, expiry, type, strike) from an OCC option symbol."""
    m = _OCC_PATTERN.match(occ.strip().upper())
    if not m:
        return None
    yy = int(m["yy"])
    year = 2000 + yy if yy < 80 else 1900 + yy
    try:
        expiry = date(year, int(m["mm"]), int(m["dd"]))
    except ValueError:
        return None
    return {
        "root": m["root"],
        "expiry": expiry,
        "type": "call" if m["cp"] == "C" else "put",
        "strike": int(m["strike"]) / 1000.0,
    }


# ── Alpaca primary source ─────────────────────────────────────────────

def _fetch_from_alpaca(ticker: str) -> pl.DataFrame | None:
    """Fetch an options-chain snapshot from Alpaca.

    Returns ``None`` on any failure (missing creds, 403, empty payload),
    so the caller can transparently fall back to yfinance.
    """
    api_key = (os.getenv("ALPACA_API_KEY_ID") or "").strip()
    api_secret = (os.getenv("ALPACA_API_SECRET_KEY") or "").strip()
    if not api_key or not api_secret:
        return None

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }

    rows: list[dict] = []
    page_token: str | None = None
    url = f"{ALPACA_OPTIONS_BASE}/snapshots/{ticker.upper()}"

    try:
        while True:
            params: dict = {"feed": "indicative", "limit": 1000}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, headers=headers, params=params, timeout=20)
            if resp.status_code in (401, 403):
                logger.warning(
                    f"Alpaca options snapshot returned {resp.status_code} "
                    f"for {ticker} — falling back"
                )
                return None
            resp.raise_for_status()
            payload = resp.json()
            snapshots = payload.get("snapshots") or {}
            for occ, snap in snapshots.items():
                parsed = parse_occ_symbol(occ)
                if not parsed or parsed["root"] != ticker.upper():
                    continue
                quote = snap.get("latestQuote") or {}
                trade = snap.get("latestTrade") or {}
                greeks = snap.get("greeks") or {}
                bid = quote.get("bp")
                ask = quote.get("ap")
                last = trade.get("p")
                mid = (
                    (bid + ask) / 2.0
                    if bid is not None and ask is not None and (bid + ask) > 0
                    else last
                )
                rows.append(
                    {
                        "symbol": occ,
                        "type": parsed["type"],
                        "strike": float(parsed["strike"]),
                        "expiry": parsed["expiry"],
                        "bid": float(bid) if bid is not None else None,
                        "ask": float(ask) if ask is not None else None,
                        "mid": float(mid) if mid is not None else None,
                        "last": float(last) if last is not None else None,
                        "iv": (
                            float(snap.get("impliedVolatility"))
                            if snap.get("impliedVolatility") is not None
                            else None
                        ),
                        "oi": int(snap.get("openInterest") or 0),
                        "volume": int(trade.get("s") or 0),
                        "delta": _f(greeks.get("delta")),
                        "gamma": _f(greeks.get("gamma")),
                        "theta": _f(greeks.get("theta")),
                        "vega": _f(greeks.get("vega")),
                    }
                )
            page_token = payload.get("next_page_token")
            if not page_token:
                break
    except requests.RequestException as exc:
        logger.warning(f"Alpaca options fetch failed for {ticker}: {exc}")
        return None

    if not rows:
        logger.info(f"Alpaca options snapshot empty for {ticker}")
        return None

    df = pl.DataFrame(rows, schema=_SCHEMA).sort(["expiry", "strike", "type"])

    # The free-tier "indicative" feed returns quotes (and sometimes Greeks)
    # but never Open Interest. Without OI we cannot compute GEX, so treat
    # such payloads as a miss and let the yfinance fallback take over.
    if int(df["oi"].sum() or 0) == 0:
        logger.info(
            f"Alpaca returned {df.height} contracts for {ticker} but no "
            "open interest — falling back to yfinance"
        )
        return None

    return df


def _f(v) -> float | None:
    """Coerce to float; treat None and NaN-like values as missing."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _i(v) -> int:
    """Coerce to int; treat None/NaN as 0."""
    if v is None:
        return 0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    if f != f:
        return 0
    return int(f)


# ── yfinance fallback ─────────────────────────────────────────────────

def _fetch_from_yfinance(ticker: str) -> pl.DataFrame | None:
    """Fetch options chains across all expirations from yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        tk = yf.Ticker(ticker.upper())
        expirations = tk.options or []
    except Exception as exc:
        logger.warning(f"yfinance options expirations failed for {ticker}: {exc}")
        return None

    if not expirations:
        return None

    rows: list[dict] = []
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            chain = tk.option_chain(exp_str)
        except Exception as exc:
            logger.warning(f"yfinance chain fetch failed for {ticker} {exp_str}: {exc}")
            continue

        for side, df in (("call", chain.calls), ("put", chain.puts)):
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                bid = r.get("bid")
                ask = r.get("ask")
                last = r.get("lastPrice")
                mid = (bid + ask) / 2.0 if (bid and ask and bid + ask > 0) else last
                rows.append(
                    {
                        "symbol": str(r.get("contractSymbol") or ""),
                        "type": side,
                        "strike": float(r.get("strike")),
                        "expiry": exp_date,
                        "bid": _f(bid),
                        "ask": _f(ask),
                        "mid": _f(mid),
                        "last": _f(last),
                        "iv": _f(r.get("impliedVolatility")),
                        "oi": _i(r.get("openInterest")),
                        "volume": _i(r.get("volume")),
                        "delta": None,
                        "gamma": None,
                        "theta": None,
                        "vega": None,
                    }
                )

    if not rows:
        return None

    return pl.DataFrame(rows, schema=_SCHEMA).sort(["expiry", "strike", "type"])


# ── Public API ────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _load_options_chain_cached(
    ticker: str,
    cache_buster: int,
) -> pl.DataFrame | None:
    """Inner cached fetch. ``cache_buster`` rolls every 15 minutes."""
    df = _fetch_from_alpaca(ticker)
    if df is not None and not df.is_empty():
        logger.info(f"Loaded {len(df)} option contracts for {ticker} from Alpaca")
        return df

    df = _fetch_from_yfinance(ticker)
    if df is not None and not df.is_empty():
        logger.info(f"Loaded {len(df)} option contracts for {ticker} from yfinance")
        return df

    return None


def load_options_chain(ticker: str) -> pl.DataFrame | None:
    """Load an options chain (15-min cache). Returns ``None`` on miss."""
    cache_buster = int(time.time() / 900)
    return _load_options_chain_cached(ticker.upper(), cache_buster)
