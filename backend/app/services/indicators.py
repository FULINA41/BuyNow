"""
技术指标计算模块
"""
import math
import pandas as pd
import numpy as np


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI (Wilder's smoothing method)"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def pct_rank_window(close: pd.Series, window: int) -> float:
    """计算价格在窗口内的分位数"""
    if len(close) < window:
        return float("nan")
    w = close.iloc[-window:]
    return w.rank(pct=True).iloc[-1].item()


def ma(series: pd.Series, n: int) -> float:
    """计算移动平均线"""
    if len(series) < n:
        return float("nan")
    return float(series.rolling(n).mean().iloc[-1])


def annualized_vol(close: pd.Series) -> float:
    """计算年化波动率"""
    rets = close.pct_change().dropna()
    if len(rets) < 50:
        return float("nan")
    return float(rets.std() * math.sqrt(252))


def drawdown_1y(close: pd.Series) -> float:
    """计算近1年回撤（负数）"""
    w = close.tail(252)
    if len(w) < 50:
        return float("nan")
    peak = w.max()
    last = w.iloc[-1]
    return float((last - peak) / peak)  # negative


def atr(df: pd.DataFrame, n: int = 14) -> float:
    """计算平均真实波幅 (ATR)"""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1
    ).max(axis=1)

    v = tr.rolling(n).mean().iloc[-1]
    return float(v) if pd.notna(v) else float("nan")
