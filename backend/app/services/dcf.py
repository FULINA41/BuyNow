"""
Two-stage Discounted Cash Flow valuation.

Stage 1: explicit forecast (default 5 years) at the company's recent
FCF growth rate, clamped to [0%, 25%].
Stage 2: Gordon-growth perpetuity at terminal_growth, clamped to
[1.5%, 3.5%].

Discounted at WACC (default 9%). Equity value = enterprise value
(no net-debt adjustment in this MVP — the existing fundamentals
service does not surface net debt). Per-share fair value =
equity_value / shares_outstanding.

The output is a "valuation floor" used by the option recommender to
upper-bound the put strike. It is intentionally simple: do not use
this as a formal valuation tool.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import lru_cache

import requests
from loguru import logger


FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"

# Sanity bounds — keep output stable when FMP returns garbage growth rates.
GROWTH_MIN = 0.0
GROWTH_MAX = 0.25
TERMINAL_MIN = 0.015
TERMINAL_MAX = 0.035

DEFAULT_HORIZON_YEARS = 5
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_WACC = 0.09


@dataclass
class DCFResult:
    """Output of a DCF run.

    Any unknown numeric is returned as ``None`` rather than ``0``,
    so the caller can tell "no FCF data" apart from "fair value is $0".
    """

    method: str
    fair_value_per_share: float | None
    fcf_baseline: float | None
    growth_rate_used: float | None
    terminal_growth: float
    wacc: float
    horizon_years: int
    shares_outstanding: float | None
    notes: list[str]


# ── FMP fetchers ──────────────────────────────────────────────────────

def _fmp_get(path: str, **params) -> list | dict | None:
    api_key = (os.getenv("FMP_API_KEY") or "").strip("'\" ")
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{FMP_STABLE_BASE}/{path}",
            params={"apikey": api_key, **params},
            timeout=10,
        )
        if resp.status_code in (401, 402, 403):
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"FMP {path} failed: {type(exc).__name__}")
        return None


def _latest_fcf(ticker: str) -> tuple[float | None, float | None]:
    """Return (latest_fcf, three_year_avg_fcf) using the FMP cash-flow stmt.

    The 3-year average smooths one-off years (litigation settlements,
    capex spikes) and gives the DCF a more stable baseline.
    """
    data = _fmp_get("cash-flow-statement", symbol=ticker, limit=4)
    if not isinstance(data, list) or not data:
        return None, None

    fcfs: list[float] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        fcf = row.get("freeCashFlow")
        if fcf is None:
            ocf = row.get("operatingCashFlow") or row.get("netCashProvidedByOperatingActivities")
            capex = row.get("capitalExpenditure")
            if ocf is not None and capex is not None:
                fcf = float(ocf) + float(capex)  # capex is negative in FMP
        if fcf is None:
            continue
        try:
            fcfs.append(float(fcf))
        except (TypeError, ValueError):
            continue

    if not fcfs:
        return None, None
    latest = fcfs[0]
    avg = sum(fcfs[: min(3, len(fcfs))]) / min(3, len(fcfs))
    return latest, avg


def _fcf_growth_rate(ticker: str) -> float | None:
    """Pull the 3y FCF CAGR if available; clamped to GROWTH bounds."""
    data = _fmp_get("financial-growth", symbol=ticker, limit=1)
    if not isinstance(data, list) or not data:
        return None
    row = data[0] if isinstance(data[0], dict) else {}
    g = (
        row.get("freeCashFlowGrowth")
        or row.get("threeYFreeCashFlowGrowthPerShare")
        or row.get("revenueGrowth")
    )
    if g is None:
        return None
    try:
        return max(GROWTH_MIN, min(GROWTH_MAX, float(g)))
    except (TypeError, ValueError):
        return None


def _shares_outstanding(ticker: str) -> float | None:
    data = _fmp_get("income-statement", symbol=ticker, limit=1)
    if not isinstance(data, list) or not data:
        return None
    row = data[0] if isinstance(data[0], dict) else {}
    s = row.get("weightedAverageShsOutDil") or row.get("weightedAverageShsOut")
    try:
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


# ── DCF core ──────────────────────────────────────────────────────────

def _two_stage_value(
    fcf0: float,
    growth: float,
    terminal_growth: float,
    wacc: float,
    horizon: int,
) -> float:
    """Sum of discounted Stage-1 FCFs + discounted Stage-2 perpetuity."""
    pv = 0.0
    fcf_t = fcf0
    for t in range(1, horizon + 1):
        fcf_t = fcf_t * (1.0 + growth)
        pv += fcf_t / ((1.0 + wacc) ** t)

    # Terminal value at end of Stage 1
    fcf_terminal_next = fcf_t * (1.0 + terminal_growth)
    terminal_value = fcf_terminal_next / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** horizon)
    return pv + pv_terminal


@lru_cache(maxsize=64)
def _compute_dcf_cached(
    ticker: str,
    cache_buster: int,
    terminal_growth: float,
    wacc: float,
    horizon_years: int,
) -> DCFResult:
    notes: list[str] = []
    latest_fcf, avg_fcf = _latest_fcf(ticker)
    fcf_baseline = avg_fcf if avg_fcf is not None else latest_fcf
    if fcf_baseline is None:
        notes.append("No FCF data available from FMP")
        return DCFResult(
            method="2-stage DCF",
            fair_value_per_share=None,
            fcf_baseline=None,
            growth_rate_used=None,
            terminal_growth=terminal_growth,
            wacc=wacc,
            horizon_years=horizon_years,
            shares_outstanding=None,
            notes=notes,
        )

    if fcf_baseline <= 0:
        notes.append(
            f"Negative FCF baseline ({fcf_baseline:,.0f}); DCF inappropriate"
        )
        return DCFResult(
            method="2-stage DCF",
            fair_value_per_share=None,
            fcf_baseline=fcf_baseline,
            growth_rate_used=None,
            terminal_growth=terminal_growth,
            wacc=wacc,
            horizon_years=horizon_years,
            shares_outstanding=None,
            notes=notes,
        )

    growth = _fcf_growth_rate(ticker)
    if growth is None:
        growth = 0.05
        notes.append("FCF growth not available; defaulted to 5%")

    if not (wacc > terminal_growth):
        terminal_growth = wacc - 0.01
        notes.append(
            f"Terminal growth >= WACC; clamped terminal to {terminal_growth:.2%}"
        )

    enterprise_value = _two_stage_value(
        fcf0=fcf_baseline,
        growth=growth,
        terminal_growth=terminal_growth,
        wacc=wacc,
        horizon=horizon_years,
    )

    shares = _shares_outstanding(ticker)
    if not shares or shares <= 0:
        notes.append("Shares outstanding not available; cannot compute per-share value")
        return DCFResult(
            method="2-stage DCF",
            fair_value_per_share=None,
            fcf_baseline=fcf_baseline,
            growth_rate_used=growth,
            terminal_growth=terminal_growth,
            wacc=wacc,
            horizon_years=horizon_years,
            shares_outstanding=None,
            notes=notes,
        )

    fair_value_per_share = enterprise_value / shares

    return DCFResult(
        method="2-stage DCF",
        fair_value_per_share=fair_value_per_share,
        fcf_baseline=fcf_baseline,
        growth_rate_used=growth,
        terminal_growth=terminal_growth,
        wacc=wacc,
        horizon_years=horizon_years,
        shares_outstanding=shares,
        notes=notes,
    )


def compute_dcf(
    ticker: str,
    *,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    wacc: float = DEFAULT_WACC,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
) -> DCFResult:
    """Public entry. Cached for 1 hour (fundamentals don't move intraday)."""
    terminal_growth = max(TERMINAL_MIN, min(TERMINAL_MAX, terminal_growth))
    cache_buster = int(time.time() / 3600)
    return _compute_dcf_cached(
        ticker.upper(), cache_buster, terminal_growth, wacc, horizon_years
    )
