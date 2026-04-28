"""
Unit tests for the GEX engine and Black-Scholes Greeks fallback.
No network, no API keys — pure algorithmic validation.
"""
from datetime import date, timedelta

import polars as pl
import pytest

from app.services.gex import compute_net_gex
from app.services.greeks import attach_greeks, black_scholes_greeks


# ── GEX engine ────────────────────────────────────────────────────────

def _synthetic_chain() -> pl.DataFrame:
    """Two strikes, four contracts. The 100-strike call has dominant OI*Γ."""
    today = date.today()
    expiry = today + timedelta(days=30)
    return pl.DataFrame(
        {
            "strike": [95.0, 95.0, 100.0, 100.0],
            "type": ["call", "put", "call", "put"],
            "gamma": [0.02, 0.02, 0.05, 0.04],
            "oi": [100, 100, 1000, 200],
            "expiry": [expiry, expiry, expiry, expiry],
            "iv": [0.30, 0.30, 0.30, 0.30],
        }
    )


def test_compute_net_gex_finds_call_dominated_wall():
    chain = _synthetic_chain()
    result = compute_net_gex(chain, spot=98.0)

    # Call contribution at 100: +1000 * 0.05 * 100 * 98 = +490_000
    # Put contribution at 100:  -200  * 0.04 * 100 * 98 =  -78_400
    # Net at 100: +411_600 — clearly the global wall.
    assert result.gamma_wall == 100.0
    # Support wall is the largest positive GEX AT-OR-BELOW spot.
    # 95 strike has +(100*0.02 - 100*0.02)*100*98 = 0; 100 is above spot
    # so support_wall should be 95 if its net is positive, else None.
    # Net at 95: 100*0.02*100*98 - 100*0.02*100*98 = 0  → not strictly positive
    # So support_wall should be None here (no support below spot).
    assert result.support_wall is None
    assert result.curve[1]["net_gex"] > result.curve[0]["net_gex"]
    assert result.spot == 98.0


def test_compute_net_gex_support_wall_picks_below_spot():
    """When the global gamma_wall is above spot, support_wall must
    pick the largest positive-GEX strike at-or-below spot instead."""
    from datetime import date, timedelta
    expiry = date.today() + timedelta(days=30)
    chain = pl.DataFrame(
        {
            "strike": [95.0, 95.0, 110.0, 110.0],
            "type":   ["call", "put", "call", "put"],
            "gamma":  [0.04,   0.01,  0.06,   0.02],
            "oi":     [500,    100,   2000,   200],
            "expiry": [expiry] * 4,
            "iv":     [0.30] * 4,
        }
    )
    result = compute_net_gex(chain, spot=100.0)

    # Global max is at 110 (call ceiling above spot).
    assert result.gamma_wall == 110.0
    # Support wall must be 95 — only positive-GEX strike at-or-below spot.
    assert result.support_wall == 95.0


def test_compute_net_gex_handles_put_dominated_strike():
    chain = pl.DataFrame(
        {
            "strike": [90.0, 90.0],
            "type": ["call", "put"],
            "gamma": [0.01, 0.05],
            "oi": [50, 1000],
            "expiry": [date.today() + timedelta(days=30)] * 2,
            "iv": [0.30, 0.30],
        }
    )
    result = compute_net_gex(chain, spot=100.0)

    # Single strike, net is negative → no positive wall, but put_support is set.
    assert result.gamma_wall is None
    assert result.put_support == 90.0
    assert result.total_gex < 0


def test_compute_net_gex_empty_input():
    empty = pl.DataFrame(
        schema={
            "strike": pl.Float64,
            "type": pl.Utf8,
            "gamma": pl.Float64,
            "oi": pl.Int64,
        }
    )
    result = compute_net_gex(empty, spot=100.0)
    assert result.curve == []
    assert result.gamma_wall is None
    assert result.total_gex == 0.0


def test_compute_net_gex_missing_columns_raises():
    bad = pl.DataFrame({"strike": [100.0], "gamma": [0.01]})
    with pytest.raises(ValueError, match="missing columns"):
        compute_net_gex(bad, spot=100.0)


# ── Black-Scholes ─────────────────────────────────────────────────────

def test_black_scholes_call_atm_delta_near_half():
    """ATM 30-day call delta should sit slightly above 0.5 with positive r."""
    g = black_scholes_greeks(
        spot=100.0,
        strikes=[100.0],
        times_to_expiry_years=[30 / 365.0],
        iv=[0.30],
        is_call=[True],
        risk_free_rate=0.045,
    )
    assert 0.50 < g["delta"][0] < 0.60


def test_black_scholes_put_call_gamma_match():
    """Gamma is symmetric in call/put for the same strike/expiry/IV."""
    args = dict(
        spot=100.0,
        strikes=[105.0],
        times_to_expiry_years=[45 / 365.0],
        iv=[0.40],
        risk_free_rate=0.045,
    )
    call = black_scholes_greeks(is_call=[True], **args)
    put = black_scholes_greeks(is_call=[False], **args)
    assert call["gamma"][0] == pytest.approx(put["gamma"][0], rel=1e-9)


def test_black_scholes_zero_T_safe():
    """Expired contracts should not divide by zero."""
    g = black_scholes_greeks(
        spot=100.0,
        strikes=[100.0],
        times_to_expiry_years=[0.0],
        iv=[0.30],
        is_call=[True],
    )
    assert g["delta"][0] == 0.0
    assert g["gamma"][0] == 0.0


def test_attach_greeks_fills_missing_columns():
    """attach_greeks should populate gamma when the input has none."""
    today = date.today()
    df = pl.DataFrame(
        {
            "strike": [95.0, 100.0, 105.0],
            "type": ["put", "call", "call"],
            "expiry": [today + timedelta(days=30)] * 3,
            "iv": [0.35, 0.30, 0.28],
        }
    )
    out = attach_greeks(df, spot=100.0, as_of=today)

    assert "gamma" in out.columns
    gammas = out["gamma"].to_list()
    assert all(g >= 0 for g in gammas)
    # Gamma peaks ATM
    assert gammas[1] > gammas[0]
    assert gammas[1] > gammas[2]
