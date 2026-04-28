"""
LLM-driven contextual risk filter for option strategies.

Given a structured strategy proposal (ticker, GEX wall, valuation
floor, recommended strike + expiry), this module asks Gemini — with
Google Search grounding enabled — to flag near-term catalysts that
quantitative models cannot see: earnings surprises, regulatory
actions, insider selling, sector rotation, social-media tail risk.

Output is a normalised JSON dict::

    {
        "risk_flags": ["Earnings on May 22", "FTC review pending"],
        "confidence_score": 0.82,
        "rationale": "...",
        "sources_consulted": ["news.example.com", ...]   # optional
    }

The function is graceful: any LLM/parse failure returns a "filter
unavailable" record with confidence_score=None, never raises.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from .LLM import query_with_grounding


_SYSTEM_PROMPT = (
    "You are a senior options-strategy risk analyst. Given a proposed "
    "Sell-Put trade and quantitative context, identify NEAR-TERM "
    "(next 30-45 days) catalysts that could invalidate the thesis. "
    "Use Google Search to verify earnings dates, regulatory actions, "
    "insider transactions, and major macro events. Your output must "
    "be a single JSON object, no commentary."
)


def _build_prompt(
    ticker: str,
    spot: float,
    gamma_wall: float | None,
    valuation_floor: float | None,
    proposed_strike: float,
    proposed_expiration: date,
    iv_rank: float | None,
) -> str:
    today = date.today().isoformat()
    return f"""
Today's date: {today}.

Proposed trade
--------------
Underlying:        {ticker}
Action:            SELL_PUT
Spot price:        ${spot:.2f}
Strike:            ${proposed_strike:.2f}
Expiration:        {proposed_expiration.isoformat()}
IV rank:           {iv_rank if iv_rank is not None else "unknown"}
Gamma wall:        {f"${gamma_wall:.2f}" if gamma_wall else "n/a"}
DCF valuation:     {f"${valuation_floor:.2f}" if valuation_floor else "n/a"}

Task
----
Search the web for any of the following that might hit BEFORE the
expiration date {proposed_expiration.isoformat()}:
1. Earnings release / pre-announcement / guidance update.
2. FDA / FTC / SEC / DoJ / antitrust actions specific to {ticker}.
3. Insider transactions (Form 4 sales > $10M in last 14 days).
4. Recent analyst downgrades or large price-target cuts.
5. Macro events affecting the sector (Fed, tariffs, supply chain).

Reply with this exact JSON schema (no extra prose, no code fences):
{{
  "risk_flags": ["short string", "..."],
  "confidence_score": 0.0_to_1.0,
  "rationale": "2-3 sentences explaining why the score is what it is",
  "sources_consulted": ["domain1.com", "..."]
}}

Rules:
- confidence_score reflects how sound the SELL_PUT is given the risks.
  1.0 = clean setup, no near-term catalysts. 0.0 = avoid trade.
- risk_flags should be specific and dated when possible
  ("Earnings on 2026-05-22", not "Upcoming earnings").
- If you cannot find concrete information, say so in rationale and
  return confidence_score: 0.5 (neutral).
""".strip()


def filter_option_risk(
    *,
    ticker: str,
    spot: float,
    gamma_wall: float | None,
    valuation_floor: float | None,
    proposed_strike: float,
    proposed_expiration: date,
    iv_rank: float | None = None,
) -> dict[str, Any]:
    """Run the grounded risk filter; return a normalised dict.

    Never raises — on any failure, returns a record with
    ``confidence_score=None`` and a single risk_flag explaining why.
    """
    prompt = _build_prompt(
        ticker=ticker,
        spot=spot,
        gamma_wall=gamma_wall,
        valuation_floor=valuation_floor,
        proposed_strike=proposed_strike,
        proposed_expiration=proposed_expiration,
        iv_rank=iv_rank,
    )

    try:
        parsed = query_with_grounding(prompt, system_instruction=_SYSTEM_PROMPT)
    except Exception as exc:
        logger.warning(f"Risk filter unavailable for {ticker}: {exc}")
        return {
            "risk_flags": [f"LLM risk filter unavailable: {type(exc).__name__}"],
            "confidence_score": None,
            "rationale": "Falling back to quantitative-only analysis.",
            "sources_consulted": [],
        }

    flags_raw = parsed.get("risk_flags") or []
    flags = [str(f) for f in flags_raw if f]
    score = parsed.get("confidence_score")
    try:
        score = max(0.0, min(1.0, float(score))) if score is not None else None
    except (TypeError, ValueError):
        score = None
    rationale = str(parsed.get("rationale") or "").strip()
    sources_raw = parsed.get("sources_consulted") or []
    sources = [str(s) for s in sources_raw if s]

    return {
        "risk_flags": flags,
        "confidence_score": score,
        "rationale": rationale,
        "sources_consulted": sources,
    }
