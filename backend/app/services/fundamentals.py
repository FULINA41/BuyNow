"""
基本面分析模块
"""
import os
import time
from functools import lru_cache

import pandas as pd
import requests
import yfinance as yf
from loguru import logger

from ..utils.formatters import safe_float

ALPACA_DATA_BASE = "https://data.alpaca.markets/v2/stocks"
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"


def _empty_fundamentals() -> dict:
    return {
        "Price": None,
        "Shares": None,
        "MarketCap": None,
        "RevenueTTM": None,
        "FCF": None,
        "PE": None,
        "PS": None,
        "PB": None,
    }


def _fmp_first_record(payload) -> dict:
    if isinstance(payload, list) and payload:
        return payload[0] if isinstance(payload[0], dict) else {}
    if isinstance(payload, dict):
        return payload
    return {}


def _fundamentals_from_fmp(ticker: str) -> dict | None:
    """
    Fetch fundamentals from FMP stable API.
    - /stable/quote             -> Price, MarketCap
    - /stable/ratios-ttm        -> PE, PS, PB, revenuePerShareTTM, freeCashFlowPerShareTTM
    - /stable/income-statement  -> weightedAverageShsOut (Shares)
    Returns a dict of the 8 fields (any missing entry is None),
    or None when FMP is unavailable / unauthorized.
    """
    api_key = (os.getenv("FMP_API_KEY") or "").strip("'\" ")
    if not api_key:
        return None

    try:
        q_res = requests.get(
            f"{FMP_STABLE_BASE}/quote",
            params={"symbol": ticker, "apikey": api_key},
            timeout=10,
        )
        r_res = requests.get(
            f"{FMP_STABLE_BASE}/ratios-ttm",
            params={"symbol": ticker, "apikey": api_key},
            timeout=10,
        )
        i_res = requests.get(
            f"{FMP_STABLE_BASE}/income-statement",
            params={"symbol": ticker, "limit": 1, "apikey": api_key},
            timeout=10,
        )
        for res in (q_res, r_res, i_res):
            if res.status_code in (401, 402, 403):
                return None
            res.raise_for_status()
        q = _fmp_first_record(q_res.json())
        r = _fmp_first_record(r_res.json())
        i = _fmp_first_record(i_res.json())
    except Exception as e:
        logger.warning(f"FMP fundamentals failed for {ticker}: {type(e).__name__}")
        return None

    price = q.get("price")
    mktcap = q.get("marketCap")

    pe = r.get("priceToEarningsRatioTTM")
    ps = r.get("priceToSalesRatioTTM")
    pb = r.get("priceToBookRatioTTM")
    rev_per_share = r.get("revenuePerShareTTM")
    fcf_per_share = r.get("freeCashFlowPerShareTTM")

    shares = i.get("weightedAverageShsOut") or i.get("weightedAverageShsOutDil")

    revenue_ttm = None
    if rev_per_share is not None and shares:
        try:
            revenue_ttm = float(rev_per_share) * float(shares)
        except (TypeError, ValueError):
            revenue_ttm = None

    fcf = None
    if fcf_per_share is not None and shares:
        try:
            fcf = float(fcf_per_share) * float(shares)
        except (TypeError, ValueError):
            fcf = None

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


def _fundamentals_from_yfinance(ticker: str) -> dict:
    """Fallback: pull fundamentals from yfinance.info / cashflow."""
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


def _latest_price_from_alpaca(ticker: str) -> float | None:
    """
    Alpaca free plan cannot access real-time data; the request window
    must end at least 15 minutes in the past. We fetch the most recent
    1-minute bar up to (now - 16 min) and return its close.
    """
    api_key = (os.getenv("ALPACA_API_KEY_ID") or "").strip()
    api_secret = (os.getenv("ALPACA_API_SECRET_KEY") or "").strip()
    if not api_key or not api_secret:
        return None

    now_utc = pd.Timestamp.now(tz="UTC")
    end = (now_utc - pd.Timedelta(minutes=16)).isoformat()
    start = (now_utc - pd.Timedelta(days=5)).isoformat()

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    params = {
        "symbols": ticker,
        "timeframe": "1Min",
        "start": start,
        "end": end,
        "adjustment": "all",
        "limit": 1000,
        "feed": "iex",
        "sort": "desc",
    }
    try:
        resp = requests.get(
            f"{ALPACA_DATA_BASE}/bars",
            headers=headers,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        bars = (resp.json().get("bars") or {}).get(ticker) or []
        if not bars:
            return None
        return safe_float(bars[0].get("c"))
    except Exception as e:
        logger.warning(f"Alpaca latest price failed for {ticker}: {type(e).__name__}")
        return None


@lru_cache(maxsize=100)
def get_fundamentals_cached(ticker: str, cache_buster: int) -> dict:
    """
    获取基本面数据（带缓存，15分钟过期）。
    优先 FMP 获取完整基本面，失败回退到 yfinance；
    Price 优先使用 Alpaca 的 15 分钟延迟收盘价（免费套餐约束）。
    """
    data = _fundamentals_from_fmp(ticker)
    if data is None:
        data = _fundamentals_from_yfinance(ticker)
    else:
        missing = [k for k, v in data.items() if v is None]
        if missing:
            yf_data = _fundamentals_from_yfinance(ticker)
            for k in missing:
                if yf_data.get(k) is not None:
                    data[k] = yf_data[k]

    alpaca_price = _latest_price_from_alpaca(ticker)
    if alpaca_price is not None:
        data["Price"] = alpaca_price

    if data.get("MarketCap") is None and data.get("Price") and data.get("Shares"):
        try:
            data["MarketCap"] = float(data["Price"]) * float(data["Shares"])
        except (TypeError, ValueError):
            pass

    return data


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
            "Method": "FCF Yield (rough)",
            "FairLow": low_mc / shares,
            "FairMid": mid_mc / shares,
            "FairHigh": high_mc / shares
        }

    # 2) PS 锚点（更普适但更粗）
    if revenue is not None and shares is not None and revenue > 0 and shares > 0:
        # 粗区间：4 / 6 / 8
        return {
            "Method": "PS Multiple (rough)",
            "FairLow": (revenue * 4.0) / shares,
            "FairMid": (revenue * 6.0) / shares,
            "FairHigh": (revenue * 8.0) / shares
        }

    return {"Method": "N/A", "FairLow": None, "FairMid": None, "FairHigh": None}
