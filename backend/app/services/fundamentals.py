"""
基本面分析模块
"""
import yfinance as yf
import pandas as pd
from ..utils.formatters import safe_float
from functools import lru_cache
import time


@lru_cache(maxsize=100)
def get_fundamentals_cached(ticker: str, cache_buster: int) -> dict:
    """
    获取基本面数据（带缓存，15分钟过期）
    """
    tk = yf.Ticker(ticker)
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares = info.get("sharesOutstanding")
    mktcap = info.get("marketCap")
    pe = info.get("trailingPE")
    ps = info.get("priceToSalesTrailing12Months")
    pb = info.get("priceToBook")

    revenue_ttm = info.get("totalRevenue")
    fcf = None

    # 尽力从 cashflow 拿 OCF 和 CapEx（可能缺失）
    try:
        cf = tk.cashflow
        if cf is not None and not cf.empty:
            col = cf.columns[0]
            ocf = cf.loc["Total Cash From Operating Activities", col] if "Total Cash From Operating Activities" in cf.index else None
            capex = cf.loc["Capital Expenditures", col] if "Capital Expenditures" in cf.index else None
            if ocf is not None and capex is not None and pd.notna(ocf) and pd.notna(capex):
                fcf = float(ocf) - float(capex)
    except Exception:
        pass

    return {
        "Price": safe_float(price),
        "Shares": safe_float(shares),
        "MarketCap": safe_float(mktcap),
        "RevenueTTM": safe_float(revenue_ttm),
        "FCF": safe_float(fcf),
        "PE": safe_float(pe),
        "PS": safe_float(ps),
        "PB": safe_float(pb),
    }


def get_fundamentals(ticker: str) -> dict:
    """获取基本面数据（带缓存控制）"""
    cache_buster = int(time.time() / 900)  # 15分钟
    return get_fundamentals_cached(ticker, cache_buster)


def rough_fair_value_range(f: dict) -> dict:
    """
    基本面锚点（粗算）：优先 FCF Yield，其次 PS
    目标：给"价值洼地加仓"一个规则锚点，不装作精确估值。
    """
    price = f.get("Price")
    shares = f.get("Shares")
    mktcap = f.get("MarketCap")
    revenue = f.get("RevenueTTM")
    fcf = f.get("FCF")

    if price is None:
        return {"Method": "N/A", "FairLow": None, "FairMid": None, "FairHigh": None}

    # 1) FCF Yield 锚点（更适合有现金流的公司）
    if fcf is not None and mktcap is not None and shares is not None and fcf > 0 and shares > 0:
        # 合理 FCF yield 区间（粗）：6% / 4.5% / 3%
        low_mc = fcf / 0.06
        mid_mc = fcf / 0.045
        high_mc = fcf / 0.03
        return {
            "Method": "FCF Yield（粗算）",
            "FairLow": low_mc / shares,
            "FairMid": mid_mc / shares,
            "FairHigh": high_mc / shares
        }

    # 2) PS 锚点（更普适但更粗）
    if revenue is not None and shares is not None and revenue > 0 and shares > 0:
        # 粗区间：4 / 6 / 8
        return {
            "Method": "PS Multiple（粗算）",
            "FairLow": (revenue * 4.0) / shares,
            "FairMid": (revenue * 6.0) / shares,
            "FairHigh": (revenue * 8.0) / shares
        }

    return {"Method": "N/A", "FairLow": None, "FairMid": None, "FairHigh": None}
