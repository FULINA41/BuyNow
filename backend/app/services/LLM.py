import os
from google import genai
from google.genai import types
from ..models.schemas import AnalysisRequest

SYSTEM_INSTRUCTION = "You are a Senior Trader specializing in fundamental analysis and valuation, your name is BuyNow AI Assistant."


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

    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
    response = client.models.generate_content_stream(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=config,
    )
    for content in response:
        if content.text:
            yield content.text
