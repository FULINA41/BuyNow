"""
Gamma Exposure (GEX) aggregation.

Inputs an options-chain DataFrame with at least
[strike, gamma, oi, type] columns and the current spot price; returns
the per-strike net dealer gamma curve and the dominant positive-GEX
strike (the "Gamma Wall").

Convention used: dealers are assumed to be net-short calls (positive
sign) and net-long puts (negative sign). The signed contribution per
contract is::

    contract_gex = oi * gamma * 100 * spot * sign(call=+1, put=-1)

The peak of the cumulative positive curve is interpreted as the
support strike where market makers' delta hedging creates upward
pressure on price.
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass
class GEXResult:
    """Curve + summary statistics for a single ticker snapshot."""

    spot: float
    curve: list[dict]            # [{strike, net_gex}, ...]  ascending strike
    gamma_wall: float | None     # strike with the largest positive net GEX (global)
    support_wall: float | None   # largest positive net GEX strike at-or-below spot
                                 # — this is the meaningful "put-side support" for
                                 # Sell-Put strategies. ``gamma_wall`` may sit above
                                 # spot (a call ceiling), in which case it is not a
                                 # support level at all.
    put_support: float | None    # strike with the most-negative net GEX (downside ceiling)
    total_gex: float             # sum of net_gex across strikes


def compute_net_gex(df: pl.DataFrame, spot: float) -> GEXResult:
    """Aggregate per-contract GEX into a per-strike curve.

    Parameters
    ----------
    df : Polars DataFrame
        Options chain. Required columns: ``strike`` (float),
        ``gamma`` (float), ``oi`` (int/float), ``type`` (str:
        "call" | "put"). Extra columns are ignored.
    spot : float
        Current underlying price. Used as the multiplier in the GEX
        notional calculation.

    Returns
    -------
    GEXResult
        Aggregated curve, dominant gamma-wall strike, put-side support,
        and total GEX. Returns an empty curve and ``None`` walls if the
        input is empty.
    """
    required = {"strike", "gamma", "oi", "type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"compute_net_gex: missing columns {missing}")

    if df.is_empty():
        return GEXResult(
            spot=spot,
            curve=[],
            gamma_wall=None,
            support_wall=None,
            put_support=None,
            total_gex=0.0,
        )

    # Per-contract signed GEX contribution
    enriched = df.with_columns(
        (
            pl.col("oi").cast(pl.Float64)
            * pl.col("gamma").cast(pl.Float64)
            * 100.0
            * pl.lit(float(spot))
            * pl.when(pl.col("type") == "call").then(1.0).otherwise(-1.0)
        ).alias("contract_gex")
    )

    by_strike = (
        enriched.group_by("strike")
        .agg(pl.sum("contract_gex").alias("net_gex"))
        .sort("strike")
    )

    curve = [
        {"strike": float(r["strike"]), "net_gex": float(r["net_gex"])}
        for r in by_strike.iter_rows(named=True)
    ]

    if not curve:
        return GEXResult(
            spot=spot,
            curve=[],
            gamma_wall=None,
            support_wall=None,
            put_support=None,
            total_gex=0.0,
        )

    gamma_wall_row = max(curve, key=lambda r: r["net_gex"])
    put_support_row = min(curve, key=lambda r: r["net_gex"])

    gamma_wall = gamma_wall_row["strike"] if gamma_wall_row["net_gex"] > 0 else None
    put_support = put_support_row["strike"] if put_support_row["net_gex"] < 0 else None

    # Support wall: the meaningful PUT-side floor — biggest positive GEX
    # at-or-below spot. When the global gamma_wall is above spot (a call
    # ceiling), this picks out the next-best supportive strike below.
    below = [r for r in curve if r["strike"] <= spot and r["net_gex"] > 0]
    support_wall = max(below, key=lambda r: r["net_gex"])["strike"] if below else None

    total_gex = sum(r["net_gex"] for r in curve)
    return GEXResult(
        spot=spot,
        curve=curve,
        gamma_wall=gamma_wall,
        support_wall=support_wall,
        put_support=put_support,
        total_gex=total_gex,
    )
