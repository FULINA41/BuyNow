"""
格式化工具函数
"""
import numpy as np


def safe_float(x):
    """安全的浮点数转换，处理 None、NaN、Inf"""
    try:
        if x is None:
            return None
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:
        return None


def normalize_columns(df):
    """标准化 DataFrame 列名（处理 MultiIndex）"""
    import pandas as pd
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df
