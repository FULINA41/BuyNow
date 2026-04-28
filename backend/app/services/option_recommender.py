"""
Sell-Put strategy recommender.

Takes the outputs of GEX (services/gex.py), DCF
(services/dcf.py), and the cached options chain
(services/options_data.py), and returns a structured recommendation:

    1. Pick a strike using the three-layer defense:
        - Value-anchored when spot < dcf * 1.5: min(dcf, gamma_wall - 1σ)
        - Growth-anchored otherwise: max(gamma_wall * 0.95, dcf or 0)
       The "growth-anchored" branch matches option_lab.md §2.3:
       when the stock trades far above its DCF, the gamma wall is a
       more meaningful floor than intrinsic value.

    2. Pick an expiration in the 30-45 day window. If an earnings
       release falls inside that window, expire 2 days before for the
       avoid-event bias (we MVP only that branch — the IV-crush
       harvest mode requires real earnings-date confidence we don't
       want to gamble on for the first version).

    3. Find the actual contract on the chain at that (strike, expiry).
       If no exact match exists, snap to the closest available strike
       with non-zero open interest.

    4. Compute IV rank (relative to 1-year IV history; we approximate
       it as percentile within the current chain when history is
       unavailable).

    5. Compute ROC for both cash-secured and Reg-T margin modes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl
from loguru import logger


# ── Tunables ──────────────────────────────────────────────────────────

EXPIRY_TARGET_MIN_DAYS = 30
EXPIRY_TARGET_MAX_DAYS = 45
GROWTH_STOCK_RATIO = 1.5         # spot / dcf threshold to switch modes
ROC_RED_FLAG_THRESHOLD = 2.0     # 200% annualised ROC -> margin leverage warning


# Aggressiveness presets — controls how much buffer we leave below spot.
# Conservative = larger σ multiplier and minimum OTM, lower premium.
# Aggressive   = smaller σ multiplier and minimum OTM, higher premium and
#                higher assignment probability.
AGGRESSIVENESS_PRESETS: dict[str, tuple[float, float]] = {
    # name: (sigma_multiplier, min_otm_fraction)
    "conservative": (0.8, 0.06),
    "moderate":     (0.5, 0.04),
    "aggressive":   (0.3, 0.025),
}
DEFAULT_AGGRESSIVENESS = "moderate"


@dataclass
class RecommendedContract:
    symbol: str | None
    strike: float
    expiration: date
    days_to_expiry: int
    type: str                       # always "put" in this MVP
    bid: float | None
    ask: float | None
    mid: float | None
    iv: float | None
    iv_rank: float | None           # 0.0 - 1.0
    open_interest: int
    delta: float | None
    gamma: float | None


@dataclass
class StrategyROC:
    margin_mode: str                # "cash_secured" | "reg_t"
    premium_per_contract: float     # dollars (mid * 100)
    capital_required: float         # dollars
    roc_per_period: float           # premium / capital
    roc_annualised: float
    margin_leverage_flag: bool      # True when ROC > ROC_RED_FLAG_THRESHOLD


@dataclass
class Recommendation:
    ticker: str
    spot: float
    strike_pick_method: str         # "value-anchored" | "growth-anchored"
    valuation_floor: float | None
    gamma_wall: float | None
    support_wall: float | None
    sigma_buffer: float | None
    final_strike: float
    contract: RecommendedContract | None
    roc_cash_secured: StrategyROC | None
    roc_reg_t: StrategyROC | None
    rationale: str


# ── Strike & expiration picking ───────────────────────────────────────

def _atm_iv(chain: pl.DataFrame, spot: float, expiry: date) -> float | None:
    """ATM IV at the chosen expiry — used as 1σ proxy for the buffer."""
    near = chain.filter(
        (pl.col("expiry") == expiry) & (pl.col("iv").is_not_null())
    )
    if near.is_empty():
        return None
    near = near.with_columns(
        (pl.col("strike") - spot).abs().alias("_dist")
    ).sort("_dist")
    return float(near["iv"][0])


def _pick_strike(
    spot: float,
    valuation_floor: float | None,
    support_wall: float | None,
    sigma_buffer: float | None,
    aggressiveness: str = DEFAULT_AGGRESSIVENESS,
) -> tuple[float, str, str]:
    """Return (strike, method, rationale_fragment).

    The wall input here is the **support_wall** (largest positive GEX
    at-or-below spot), not the global gamma_wall — a global max above
    spot is a CALL ceiling and is meaningless for Sell-Put strikes.

    Two protective candidates are computed:
        wall_strike = support_wall - k·σ   (anchored to dealer support)
        spot_floor  = spot - max(k·σ, m·spot)  (always ≥ m% below spot)

    where ``k`` and ``m`` are the aggressiveness preset
    (``moderate``: 0.5σ, 4%). In **growth-anchored** mode we take the
    *less conservative* of the two (``max``) — both already provide
    protection independently, so stacking via ``min`` over-shoots. In
    **value-anchored** mode we take ``min`` because DCF is a hard
    "I'd own at this price" ceiling that should not be exceeded.
    """
    sigma_mult, min_otm = AGGRESSIVENESS_PRESETS.get(
        aggressiveness, AGGRESSIVENESS_PRESETS[DEFAULT_AGGRESSIVENESS]
    )

    # Hard minimum buffer below spot.
    min_buffer = max((sigma_buffer or 0.0) * sigma_mult, min_otm * spot)
    spot_floor = spot - min_buffer

    # Wall-based candidate (only valid if support_wall is at-or-below spot)
    if support_wall is not None and sigma_buffer is not None:
        wall_strike = support_wall - sigma_mult * sigma_buffer
    elif support_wall is not None:
        wall_strike = support_wall
    else:
        wall_strike = None

    is_value_stock = (
        valuation_floor is not None
        and valuation_floor > 0
        and spot / valuation_floor <= GROWTH_STOCK_RATIO
    )

    if is_value_stock:
        # DCF is a hard ceiling — strike never exceeds fair value.
        candidates = [c for c in (valuation_floor, wall_strike, spot_floor) if c is not None]
        strike = min(candidates)
        parts = [f"DCF=${valuation_floor:.2f}"]
        if wall_strike is not None:
            parts.append(f"SupportWall - {sigma_mult}σ=${wall_strike:.2f}")
        parts.append(f"Spot - buffer=${spot_floor:.2f}")
        rationale = (
            f"Value-anchored ({aggressiveness}): strike = min({', '.join(parts)})."
        )
        return strike, "value-anchored", rationale

    # Growth-anchored: take the looser of the two protections.
    if wall_strike is not None:
        strike = max(wall_strike, spot_floor)
        rationale = (
            f"Growth-anchored ({aggressiveness}): spot (${spot:.2f}) >> DCF "
            f"(${valuation_floor or 0:.2f}); strike = max(SupportWall - "
            f"{sigma_mult}σ=${wall_strike:.2f}, Spot - buffer=${spot_floor:.2f})."
        )
    else:
        strike = spot_floor
        rationale = (
            f"Growth-anchored ({aggressiveness}): no put-side gamma support; "
            f"defaulting to Spot - buffer=${spot_floor:.2f}."
        )
    if valuation_floor and valuation_floor > 0:
        strike = max(strike, valuation_floor)
    return strike, "growth-anchored", rationale


def _pick_expiry(
    chain: pl.DataFrame,
    today: date,
    earnings_date: date | None,
) -> date | None:
    """Choose an expiration in the 30-45 day window of available dates."""
    expiries = sorted(set(chain["expiry"].to_list()))
    if not expiries:
        return None

    target_low = today + timedelta(days=EXPIRY_TARGET_MIN_DAYS)
    target_high = today + timedelta(days=EXPIRY_TARGET_MAX_DAYS)

    in_window = [e for e in expiries if target_low <= e <= target_high]
    chosen: date | None = None
    if in_window:
        chosen = in_window[len(in_window) // 2]  # middle of window
    else:
        future = [e for e in expiries if e >= today]
        if future:
            chosen = min(future, key=lambda e: abs((e - target_low).days))

    if chosen is None:
        return None

    # Earnings avoidance: if earnings falls strictly inside the chosen
    # contract's life, snap to the latest expiry that lands ≥2 trading
    # days before earnings.
    if earnings_date and today <= earnings_date <= chosen:
        cutoff = earnings_date - timedelta(days=2)
        prior = [e for e in expiries if today <= e <= cutoff]
        if prior:
            return max(prior)

    return chosen


def _snap_to_contract(
    chain: pl.DataFrame,
    target_strike: float,
    expiry: date,
    side: str = "put",
) -> dict | None:
    """Find the closest available put on the chain at ``expiry``."""
    candidates = chain.filter(
        (pl.col("expiry") == expiry)
        & (pl.col("type") == side)
        & (pl.col("oi") > 0)
    )
    if candidates.is_empty():
        candidates = chain.filter(
            (pl.col("expiry") == expiry) & (pl.col("type") == side)
        )
    if candidates.is_empty():
        return None
    candidates = candidates.with_columns(
        (pl.col("strike") - target_strike).abs().alias("_dist")
    ).sort("_dist")
    return candidates.head(1).to_dicts()[0]


def _iv_rank(chain: pl.DataFrame, contract_iv: float | None) -> float | None:
    """Approximate IV rank as the contract's percentile inside the chain.

    A real IV-rank uses 1-year IV history — we don't store that yet —
    so this is a coarse proxy. Still useful for relative comparison
    across contracts on the same chain.
    """
    if contract_iv is None:
        return None
    ivs = chain["iv"].drop_nulls().to_list()
    if not ivs:
        return None
    below = sum(1 for v in ivs if v <= contract_iv)
    return round(below / len(ivs), 4)


# ── ROC ───────────────────────────────────────────────────────────────

def _compute_roc(
    *,
    premium_dollars: float,
    capital_required: float,
    days_to_expiry: int,
) -> tuple[float, float, bool]:
    """Return (period_roc, annualised_roc, margin_red_flag)."""
    if capital_required <= 0 or days_to_expiry <= 0:
        return 0.0, 0.0, False
    period_roc = premium_dollars / capital_required
    annualised = period_roc * (365.0 / days_to_expiry)
    return period_roc, annualised, annualised > ROC_RED_FLAG_THRESHOLD


def _roc_cash_secured(
    contract: RecommendedContract,
    days: int,
) -> StrategyROC | None:
    if contract.mid is None:
        return None
    premium = contract.mid * 100.0
    capital = contract.strike * 100.0
    period, ann, flag = _compute_roc(
        premium_dollars=premium,
        capital_required=capital,
        days_to_expiry=days,
    )
    return StrategyROC(
        margin_mode="cash_secured",
        premium_per_contract=premium,
        capital_required=capital,
        roc_per_period=period,
        roc_annualised=ann,
        margin_leverage_flag=flag,
    )


def _roc_reg_t(
    contract: RecommendedContract,
    spot: float,
    days: int,
) -> StrategyROC | None:
    """Reg-T short put margin (rough): max(20% spot - OTM, 10% strike) + premium.

    The standard FINRA short-put formula. We keep the floor (10% strike)
    so deep-OTM puts don't end up with absurd ROC numbers from
    near-zero capital requirements.
    """
    if contract.mid is None:
        return None
    premium = contract.mid * 100.0
    otm_amount = max(spot - contract.strike, 0.0)
    margin_per_share = max(0.20 * spot - otm_amount, 0.10 * contract.strike)
    capital = margin_per_share * 100.0 + premium  # premium is collateral too
    period, ann, flag = _compute_roc(
        premium_dollars=premium,
        capital_required=capital,
        days_to_expiry=days,
    )
    return StrategyROC(
        margin_mode="reg_t",
        premium_per_contract=premium,
        capital_required=capital,
        roc_per_period=period,
        roc_annualised=ann,
        margin_leverage_flag=flag,
    )


# ── Public entry ──────────────────────────────────────────────────────

def build_recommendation(
    *,
    ticker: str,
    spot: float,
    chain: pl.DataFrame,
    gamma_wall: float | None,
    support_wall: float | None = None,
    valuation_floor: float | None,
    earnings_date: date | None = None,
    today: date | None = None,
    aggressiveness: str = DEFAULT_AGGRESSIVENESS,
) -> Recommendation:
    """Compose the full recommendation for one ticker.

    All three pillars (chain, GEX, DCF) are passed in — this function
    does no fetching, it just composes. Returns ``contract=None`` and
    ROC=None when no suitable contract exists.
    """
    today = today or date.today()
    expiry = _pick_expiry(chain, today=today, earnings_date=earnings_date)
    if expiry is None:
        return Recommendation(
            ticker=ticker,
            spot=spot,
            strike_pick_method="unavailable",
            valuation_floor=valuation_floor,
            gamma_wall=gamma_wall,
            support_wall=support_wall,
            sigma_buffer=None,
            final_strike=math.nan,
            contract=None,
            roc_cash_secured=None,
            roc_reg_t=None,
            rationale="No tradeable expiry within 30-45 day window.",
        )

    atm_iv = _atm_iv(chain, spot=spot, expiry=expiry)
    days_to_expiry = (expiry - today).days
    sigma_buffer = (
        spot * atm_iv * math.sqrt(max(days_to_expiry, 1) / 365.0)
        if atm_iv else None
    )

    # Prefer the put-side support wall (positive GEX below spot) for
    # strike selection; fall back to the global gamma_wall only when no
    # below-spot positive GEX exists.
    wall_for_strike = support_wall if support_wall is not None else gamma_wall
    target_strike, method, rationale_strike = _pick_strike(
        spot=spot,
        valuation_floor=valuation_floor,
        support_wall=wall_for_strike,
        sigma_buffer=sigma_buffer,
        aggressiveness=aggressiveness,
    )

    contract_dict = _snap_to_contract(chain, target_strike, expiry, "put")
    if contract_dict is None:
        return Recommendation(
            ticker=ticker,
            spot=spot,
            strike_pick_method=method,
            valuation_floor=valuation_floor,
            gamma_wall=gamma_wall,
            support_wall=support_wall,
            sigma_buffer=sigma_buffer,
            final_strike=target_strike,
            contract=None,
            roc_cash_secured=None,
            roc_reg_t=None,
            rationale=rationale_strike + " No put contract found at this strike/expiry.",
        )

    iv_rank = _iv_rank(chain, contract_dict.get("iv"))
    contract = RecommendedContract(
        symbol=contract_dict.get("symbol"),
        strike=float(contract_dict["strike"]),
        expiration=expiry,
        days_to_expiry=days_to_expiry,
        type="put",
        bid=contract_dict.get("bid"),
        ask=contract_dict.get("ask"),
        mid=contract_dict.get("mid"),
        iv=contract_dict.get("iv"),
        iv_rank=iv_rank,
        open_interest=int(contract_dict.get("oi") or 0),
        delta=contract_dict.get("delta"),
        gamma=contract_dict.get("gamma"),
    )

    roc_cs = _roc_cash_secured(contract, days_to_expiry)
    roc_rt = _roc_reg_t(contract, spot, days_to_expiry)

    rationale = rationale_strike
    if earnings_date:
        rationale += f" Earnings calendar: {earnings_date.isoformat()}."
    if not (EXPIRY_TARGET_MIN_DAYS <= days_to_expiry <= EXPIRY_TARGET_MAX_DAYS):
        rationale += (
            f" Note: nearest expiry was {days_to_expiry}d (target window 30-45)."
        )

    return Recommendation(
        ticker=ticker,
        spot=spot,
        strike_pick_method=method,
        valuation_floor=valuation_floor,
        gamma_wall=gamma_wall,
        support_wall=support_wall,
        sigma_buffer=sigma_buffer,
        final_strike=contract.strike,
        contract=contract,
        roc_cash_secured=roc_cs,
        roc_reg_t=roc_rt,
        rationale=rationale,
    )
