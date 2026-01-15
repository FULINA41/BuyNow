"""
信号生成逻辑模块
"""
import pandas as pd
from .indicators import rsi_wilder, pct_rank_window


def signal_abc(df: pd.DataFrame) -> dict:
    """
    ABC 信号系统：
    A: 位置偏低（分位低）
    B: 情绪偏冷（RSI低）
    C: 回暖（RSI拐头向上）
    """
    close = df["Close"].dropna().astype(float)
    rsi = rsi_wilder(close, 14)

    last = float(close.iloc[-1])
    rsi_last = float(rsi.iloc[-1])

    pr_3y = pct_rank_window(close, 756)   # ~3y
    pr_5y = pct_rank_window(close, 1260)  # ~5y

    # A：位置偏低（分位低）
    A = (pd.notna(pr_3y) and pr_3y < 0.30) or (pd.notna(pr_5y) and pr_5y < 0.30)

    # B：情绪偏冷（RSI低）
    B = (rsi_last < 35)

    # C：回暖（RSI拐头向上）
    rsi_dropna = rsi.dropna()
    C = False
    if len(rsi_dropna) >= 2:
        C = float(rsi_dropna.iloc[-1]) > float(rsi_dropna.iloc[-2])

    if A and B and C:
        sig = "加仓"
    elif A and B:
        sig = "建仓"
    elif A or B:
        sig = "试探"
    else:
        sig = "观察"

    return {
        "Signal": sig,
        "Last": last,
        "RSI": rsi_last,
        "Pct3Y": pr_3y if pd.notna(pr_3y) else None,
        "Pct5Y": pr_5y if pd.notna(pr_5y) else None,
        "A_pos": A,
        "B_rsi": B,
        "C_turn": C
    }
