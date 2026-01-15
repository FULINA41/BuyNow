"""
买入区间计算模块
"""
import pandas as pd
import numpy as np
from .indicators import atr, ma
from ..utils.formatters import safe_float


def buy_zones(df: pd.DataFrame) -> dict:
    """
    计算三个买入区间：保守、标准、激进
    基于 ATR 和 MA200 偏离度
    """
    close = df["Close"].dropna().astype(float)
    last = float(close.iloc[-1])

    a = atr(df, 14)
    a = safe_float(a)

    atr_pct = (a / last) if (a is not None and last > 0) else 0.0

    # 带宽：至少 6% 或 1.8*ATR（两者取更大）
    width = max((1.8 * a) if a is not None else 0.0, last * max(0.06, 1.2 * atr_pct))

    # 中心：偏向"回调买"，价格越高于MA200，中心越往下
    ma200 = ma(close, 200)
    dev200 = ((last - ma200) / ma200) if pd.notna(ma200) else 0.0
    center_disc = 0.10 + float(np.clip(dev200, -0.2, 0.2)) * 0.10
    center_disc = float(np.clip(center_disc, 0.06, 0.18))
    center = last * (1 - center_disc)

    conservative = (center + 0.6 * width, center + 1.2 * width)  # 更稳
    neutral = (center - 0.4 * width, center + 0.4 * width)       # 主力区
    aggressive = (center - 1.2 * width, center - 0.6 * width)     # 抄底带

    def clamp(r):
        lo, hi = r
        lo = max(float(lo), 0.01)
        hi = max(float(hi), 0.01)
        if lo > hi:
            lo, hi = hi, lo
        return (lo, hi)

    return {
        "ATR14": a,
        "Last": last,
        "Conservative": clamp(conservative),
        "Neutral": clamp(neutral),
        "Aggressive": clamp(aggressive)
    }


def add_levels(last: float, zones: dict, fair: dict) -> dict:
    """
    计算加仓位置
    """
    n_lo, n_hi = zones["Neutral"]
    a_lo, a_hi = zones["Aggressive"]

    first_add = n_lo                   # 标准区下沿
    pullback_add = (a_lo + a_hi) / 2   # 抄底带中点

    fair_low = safe_float(fair.get("FairLow"))
    fair_mid = safe_float(fair.get("FairMid"))

    value_pocket = None
    rule = None
    if fair_low is not None and fair_low > 0:
        value_pocket = fair_low * 0.90
        rule = "价格 ≤ 0.9 × FairLow（估值折扣）"
    elif fair_mid is not None and fair_mid > 0:
        value_pocket = fair_mid * 0.70
        rule = "价格 ≤ 0.7 × FairMid（估值折扣）"

    return {
        "FirstAdd": first_add,
        "PullbackAdd": pullback_add,
        "ValuePocketAdd": value_pocket,
        "ValuePocketRule": rule
    }
