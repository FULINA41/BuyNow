"""
数据加载模块（带缓存）
"""
import yfinance as yf
import pandas as pd
from functools import lru_cache
import time
from ..utils.formatters import normalize_columns


@lru_cache(maxsize=100)
def load_price_cached(ticker: str, start: str, cache_buster: int) -> pd.DataFrame:
    """加载价格数据（带缓存，15分钟过期）"""
    df = yf.download(ticker, start=start, progress=False, auto_adjust=False)
    df = normalize_columns(df)
    return df


def load_price(ticker: str, start: str) -> pd.DataFrame:
    """加载价格数据（带缓存控制）"""
    cache_buster = int(time.time() / 900)  # 15分钟
    return load_price_cached(ticker, start, cache_buster)
