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

    # 信号1：死亡交叉（当前50下穿200）
    is_death_cross = (pd.notna(ma50) and pd.notna(ma200) and ma50.iloc[-1] < ma200.iloc[-1]) and (ma50.iloc[-2] >= ma200.iloc[-2])

    # 信号2：距离过远（比如50比200低了10%以上）
    distance = (ma50.iloc[-1] - ma200.iloc[-1]) / ma200.iloc[-1]
    is_crashing = distance < -0.10

    vol = annualized_vol(close)      # annualized
    dd = drawdown_1y(close)          # negative

    # 可解释风险分级：波动+回撤+趋势
    score = 0

    #annualized vol
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
    
    if is_crashing:
        score+=2

    if score>=5 and is_death_cross:
        lvl = "🔴 High Risk(Death Cross)"
    elif score >= 5:
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
