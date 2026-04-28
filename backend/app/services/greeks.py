"""
Black-Scholes Greeks (vectorized fallback).

Used when the upstream options-chain provider does not return Greeks
(yfinance does not; Alpaca's options snapshot endpoint does, when
available). Outputs delta / gamma / theta / vega per-row.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import polars as pl


SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / SQRT_2PI


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    # math.erf is not vectorized; numpy has no erf, but scipy is heavy.
    # Use the Abramowitz & Stegun approximation (max abs error ~7.5e-8).
    # Equivalent to 0.5 * (1 + erf(x / sqrt(2))).
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def black_scholes_greeks(
    spot: float,
    strikes: np.ndarray,
    times_to_expiry_years: np.ndarray,
    iv: np.ndarray,
    is_call: np.ndarray,
    risk_free_rate: float = 0.045,
) -> dict[str, np.ndarray]:
    """
    Compute Black-Scholes delta, gamma, theta (per-day), vega (per-1%-IV).

    Inputs are aligned arrays of length N. ``is_call`` is bool/0-1 mask.
    Time to expiry in years (e.g. 30 days = 30/365). Implied vol as a
    decimal (0.30 = 30%). Returns a dict of numpy arrays.

    Gamma and vega are call/put-symmetric. Delta and theta differ.
    Rows with non-positive T or IV produce zeros (avoids div/0).
    """
    S = float(spot)
    K = np.asarray(strikes, dtype=np.float64)
    T = np.asarray(times_to_expiry_years, dtype=np.float64)
    sigma = np.asarray(iv, dtype=np.float64)
    is_call_f = np.asarray(is_call, dtype=np.float64)
    r = float(risk_free_rate)

    valid = (T > 0) & (sigma > 0) & (K > 0)
    safe_T = np.where(valid, T, 1.0)
    safe_sigma = np.where(valid, sigma, 1e-6)

    sqrt_T = np.sqrt(safe_T)
    d1 = (np.log(S / K) + (r + 0.5 * safe_sigma * safe_sigma) * safe_T) / (
        safe_sigma * sqrt_T
    )
    d2 = d1 - safe_sigma * sqrt_T

    pdf_d1 = _norm_pdf(d1)
    cdf_d1 = _norm_cdf(d1)
    cdf_d2 = _norm_cdf(d2)

    call_delta = cdf_d1
    put_delta = cdf_d1 - 1.0
    delta = np.where(is_call_f > 0.5, call_delta, put_delta)

    gamma = pdf_d1 / (S * safe_sigma * sqrt_T)
    vega_per_1pct = S * pdf_d1 * sqrt_T / 100.0  # per 1% IV change

    discount = np.exp(-r * safe_T)
    call_theta_year = (
        -S * pdf_d1 * safe_sigma / (2.0 * sqrt_T) - r * K * discount * cdf_d2
    )
    put_theta_year = (
        -S * pdf_d1 * safe_sigma / (2.0 * sqrt_T)
        + r * K * discount * _norm_cdf(-d2)
    )
    theta_year = np.where(is_call_f > 0.5, call_theta_year, put_theta_year)
    theta_per_day = theta_year / 365.0

    delta = np.where(valid, delta, 0.0)
    gamma = np.where(valid, gamma, 0.0)
    theta_per_day = np.where(valid, theta_per_day, 0.0)
    vega_per_1pct = np.where(valid, vega_per_1pct, 0.0)

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta_per_day,
        "vega": vega_per_1pct,
    }


def attach_greeks(
    df: pl.DataFrame,
    spot: float,
    risk_free_rate: float = 0.045,
    as_of: date | None = None,
) -> pl.DataFrame:
    """
    Attach delta/gamma/theta/vega columns to a Polars options DataFrame.

    Required input columns: strike, expiry (Date), iv, type ("call"/"put").
    Computes Greeks for any rows where the column is missing or null;
    rows that already have a numeric Greek are preserved.
    """
    required = {"strike", "expiry", "iv", "type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"attach_greeks: missing columns {missing}")

    today = as_of or date.today()
    expiries = df["expiry"].to_list()
    days = np.array(
        [(d - today).days if d is not None else 0 for d in expiries],
        dtype=np.float64,
    )
    T = np.maximum(days, 0.0) / 365.0

    strikes = df["strike"].to_numpy().astype(np.float64)
    iv = df["iv"].to_numpy().astype(np.float64)
    is_call = (df["type"] == "call").to_numpy()

    g = black_scholes_greeks(
        spot=spot,
        strikes=strikes,
        times_to_expiry_years=T,
        iv=iv,
        is_call=is_call,
        risk_free_rate=risk_free_rate,
    )

    out_cols = []
    for name in ("delta", "gamma", "theta", "vega"):
        computed = pl.Series(name, g[name], dtype=pl.Float64)
        if name in df.columns:
            existing = df[name].cast(pl.Float64, strict=False)
            merged = pl.Series(
                name,
                np.where(np.isnan(existing.to_numpy()), g[name], existing.to_numpy()),
                dtype=pl.Float64,
            )
            out_cols.append(merged)
        else:
            out_cols.append(computed)

    return df.with_columns(out_cols)
