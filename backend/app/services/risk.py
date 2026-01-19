"""
风险评估模块
"""
import pandas as pd
from .indicators import ma, annualized_vol, drawdown_1y
from ..utils.formatters import safe_float


def risk_level(df: pd.DataFrame) -> dict:
    """
    风险评级：基于波动率、回撤、趋势
    分数越高风险越大
    """
    close = df["Close"].dropna().astype(float)

    last = float(close.iloc[-1])
    ma50 = ma(close, 50)
    ma200 = ma(close, 200)
    trend_up = (pd.notna(ma50) and pd.notna(ma200) and ma50 > ma200)

    vol = annualized_vol(close)      # annualized
    dd = drawdown_1y(close)          # negative

    # 可解释风险分级：波动+回撤+趋势
    score = 0

    if pd.notna(vol):
        if vol > 0.60:
            score += 3
        elif vol > 0.45:
            score += 2
        elif vol > 0.30:
            score += 1

    if pd.notna(dd):
        if dd < -0.40:
            score += 3
        elif dd < -0.30:
            score += 2
        elif dd < -0.15:
            score += 1

    if not trend_up:
        score += 1

    if score >= 5:
        lvl = "🔴 High Risk"
    elif score >= 3:
        lvl = "🟡 Medium Risk"
    else:
        lvl = "🟢 Low Risk"

    return {
        "Risk": lvl,
        "RiskScore": score,
        "TrendUp": trend_up,
        "MA50": safe_float(ma50),
        "MA200": safe_float(ma200),
        "Vol": safe_float(vol),
        "DD1Y": safe_float(dd),
        "Last": last
    }
