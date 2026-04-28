import json
import os
import re

from google import genai
from google.genai import types
from loguru import logger

from ..models.schemas import AnalysisRequest

SYSTEM_INSTRUCTION = "You are a Senior Trader specializing in fundamental analysis and valuation, your name is BuyNow AI Assistant."

GROUNDED_MODEL = os.getenv("GEMINI_GROUNDING_MODEL", "gemini-2.5-flash")


async def analyze_stock_fundamentals_llm(request: AnalysisRequest):
    """
    Analyze the stock fundamentals using LLM
    """
    api_key = os.environ.get("GEMINI_API_KEY") or ""
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    client = genai.Client(api_key=api_key)

    ticker = request.ticker
    risk_appetite = request.mode
    prompt = f'Role: Act as a Senior Equity Research Analyst specializing in fundamental analysis and valuation.Task: Provide a deep-dive fundamental analysis for the stock ticker: {ticker}.Context: My risk appetite is {risk_appetite}.Analysis Requirements:Valuation & Metrics: Analyze the current $P/E$ ratio relative to its 5-year historical average and its primary industry peers. Evaluate if the stock is undervalued, overvalued, or fairly priced based on current earnings and growth.Future Growth Prospects: Identify the core "moats" and growth drivers for the next 3–5 years. Focus on R&D, market share expansion, and upcoming product pipelines.Macro & Geopolitical Impact: Analyze how current international tensions, trade policies, and global supply chain shifts specifically affect this company\'s operations and revenue.Risk Alignment: Based on my {risk_appetite} profile, identify the biggest "Red Flags" or "Bear Case" scenarios that could lead to a significant drawdown.Financial Health: Briefly comment on the debt-to-equity ratio and free cash flow (FCF) trends.Output Format:Use a structured layout with bold headings.Provide a "Bull Case" vs. "Bear Case" summary.Conclude with a "Risk-Adjusted Verdict" specifically tailored to my risk appetite.'

    config =  types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
    response = await client.aio.models.generate_content_stream(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=config,
    )
    async for content in response:
        if content.text:
            yield content.text


def _extract_json_object(text: str) -> dict | None:
    """Pull the first balanced JSON object out of free-form LLM output.

    Gemini may wrap JSON in fenced code blocks or prefix a sentence
    even when ``response_mime_type=application/json`` is set, especially
    when grounding is enabled. We strip code fences and locate the
    outermost ``{...}`` span before parsing.
    """
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def query_with_grounding(
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str | None = None,
    enable_search: bool = True,
) -> dict:
    """Run a one-shot grounded Gemini query that returns a JSON object.

    Returns the parsed JSON dict. Raises ``ValueError`` when the API
    key is missing or no JSON could be extracted from the response.

    Note: Gemini does not allow combining ``response_mime_type=
    application/json`` with the google_search tool, so we rely on a
    strong instruction in the prompt + ``_extract_json_object`` to
    recover the structured payload.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or ""
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    client = genai.Client(api_key=api_key)
    tools = []
    if enable_search:
        try:
            tools.append(types.Tool(google_search=types.GoogleSearch()))
        except AttributeError:
            logger.warning(
                "google_search tool not available in this google-genai "
                "version; running without grounding"
            )
            tools = []

    config = types.GenerateContentConfig(
        system_instruction=system_instruction or SYSTEM_INSTRUCTION,
        tools=tools or None,
        temperature=0.2,
    )

    resp = client.models.generate_content(
        model=model or GROUNDED_MODEL,
        contents=prompt,
        config=config,
    )

    text = getattr(resp, "text", None) or ""
    parsed = _extract_json_object(text)
    if parsed is None:
        logger.warning(
            f"Grounded LLM returned non-JSON output (first 200 chars): {text[:200]!r}"
        )
        raise ValueError("Grounded LLM did not return a parseable JSON object")
    return parsed
