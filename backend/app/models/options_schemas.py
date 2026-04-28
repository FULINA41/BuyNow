"""
Pydantic schemas for the Option Lab API.

Phase 1: GEX response.
Phase 2: full Sell-Put recommendation (strike, expiration, ROC,
         risk_flags, confidence_score) and the request payload that
         drives it.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class GEXCurvePoint(BaseModel):
    """Single (strike, net_gex) point on the dealer-gamma curve."""

    strike: float
    net_gex: float


class GEXResponse(BaseModel):
    """GEX snapshot for one ticker."""

    ticker: str = Field(..., description="Underlying symbol")
    spot: float = Field(..., description="Current underlying price used in the GEX notional")
    as_of: datetime = Field(..., description="UTC timestamp of the snapshot")
    contracts_loaded: int = Field(..., description="Number of contracts in the source chain")
    expiry_filter: date | None = Field(
        None,
        description="If set, only contracts expiring on or before this date were aggregated",
    )
    curve: list[GEXCurvePoint] = Field(
        ..., description="Per-strike net dealer gamma exposure, ascending by strike"
    )
    gamma_wall: float | None = Field(
        None,
        description="Strike with the largest positive net GEX (global). May sit above spot, in which case it is a call ceiling rather than a put support",
    )
    support_wall: float | None = Field(
        None,
        description="Largest positive net GEX strike at-or-below spot — the meaningful PUT-side support floor",
    )
    put_support: float | None = Field(
        None,
        description="Strike with the most-negative net GEX — interpreted as downside ceiling",
    )
    total_gex: float = Field(..., description="Sum of net_gex across all strikes")
    source: str = Field(..., description="Data source: alpaca | yfinance | mixed")


# ── Phase 2: recommendation ──────────────────────────────────────────

class RecommendationRequest(BaseModel):
    """Optional knobs for the recommendation endpoint."""

    margin_mode: Literal["cash_secured", "reg_t", "both"] = Field(
        "both", description="Which capital model to compute ROC against"
    )
    aggressiveness: Literal["conservative", "moderate", "aggressive"] = Field(
        "moderate",
        description=(
            "Strike-selection aggressiveness. moderate (default) ≈ 0.5σ buffer "
            "and 4% min OTM; conservative widens to 0.8σ / 6%; aggressive "
            "tightens to 0.3σ / 2.5%."
        ),
    )
    enable_llm_filter: bool = Field(
        True,
        description="If false, skip the Gemini grounding call (faster, cheaper)",
    )
    risk_free_rate: float = Field(
        0.045, ge=0.0, le=0.20, description="r used in Black-Scholes Greeks fallback"
    )
    wacc: float = Field(
        0.09, ge=0.04, le=0.20, description="Discount rate used in the DCF"
    )


class RecommendedContractModel(BaseModel):
    symbol: str | None
    strike: float
    expiration: date
    days_to_expiry: int
    type: str
    bid: float | None
    ask: float | None
    mid: float | None
    iv: float | None
    iv_rank: float | None
    open_interest: int
    delta: float | None
    gamma: float | None


class StrategyROCModel(BaseModel):
    margin_mode: str
    premium_per_contract: float
    capital_required: float
    roc_per_period: float
    roc_annualised: float
    margin_leverage_flag: bool


class DCFSummaryModel(BaseModel):
    method: str
    fair_value_per_share: float | None
    fcf_baseline: float | None
    growth_rate_used: float | None
    terminal_growth: float
    wacc: float
    horizon_years: int
    notes: list[str]


class RiskFilterModel(BaseModel):
    risk_flags: list[str]
    confidence_score: float | None
    rationale: str
    sources_consulted: list[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    ticker: str
    action: Literal["SELL_PUT"] = "SELL_PUT"
    spot: float
    as_of: datetime
    strike_pick_method: str
    valuation_floor: float | None
    gamma_wall: float | None
    support_wall: float | None
    sigma_buffer: float | None
    final_strike: float
    rationale: str
    contract: RecommendedContractModel | None
    roc_cash_secured: StrategyROCModel | None
    roc_reg_t: StrategyROCModel | None
    dcf: DCFSummaryModel
    risk_filter: RiskFilterModel
