"""
Vectorized Polars feature engineering for the Global Panel Model.
Operates on a stacked panel DataFrame (multiple tickers, long format).
"""
import json
from pathlib import Path

import polars as pl

FEATURE_COLS = [
    "returns",
    "log_returns",
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "volatility_20d",
    "close_sma20_ratio",
    "close_sma50_ratio",
    "volume_sma20_ratio",
]


def calculate_features_polars(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate technical features for a stacked panel dataframe.
    Expects columns: ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume'].
    All calculations are partitioned by ticker via .over("ticker").
    """
    RSI_PERIOD = 14
    MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
    VOL_WINDOW = 20

    df = df.sort("ticker", "date")

    # --- Daily returns ---
    prev_close = pl.col("close").shift(1).over("ticker")
    df = df.with_columns(
        (pl.col("close") / prev_close - 1.0).alias("returns"),
        (pl.col("close") / prev_close).log().alias("log_returns"),
    )

    # --- RSI (Wilder's smoothing, alpha = 1/period) ---
    delta = pl.col("close").diff().over("ticker")
    df = df.with_columns(
        delta.clip(lower_bound=0)
        .ewm_mean(alpha=1.0 / RSI_PERIOD, adjust=False)
        .over("ticker")
        .alias("_avg_gain"),
        (-delta)
        .clip(lower_bound=0)
        .ewm_mean(alpha=1.0 / RSI_PERIOD, adjust=False)
        .over("ticker")
        .alias("_avg_loss"),
    )
    df = df.with_columns(
        (100.0 - 100.0 / (1.0 + pl.col("_avg_gain") / pl.col("_avg_loss"))).alias(
            "rsi_14"
        ),
    ).drop("_avg_gain", "_avg_loss")

    # --- MACD (12 / 26 / 9) ---
    df = df.with_columns(
        pl.col("close")
        .ewm_mean(span=MACD_FAST, adjust=False)
        .over("ticker")
        .alias("_ema_fast"),
        pl.col("close")
        .ewm_mean(span=MACD_SLOW, adjust=False)
        .over("ticker")
        .alias("_ema_slow"),
    )
    df = df.with_columns(
        (pl.col("_ema_fast") - pl.col("_ema_slow")).alias("macd_line"),
    )
    df = df.with_columns(
        pl.col("macd_line")
        .ewm_mean(span=MACD_SIG, adjust=False)
        .over("ticker")
        .alias("macd_signal"),
    )
    df = df.with_columns(
        (pl.col("macd_line") - pl.col("macd_signal")).alias("macd_hist"),
    ).drop("_ema_fast", "_ema_slow")

    # --- 20-day rolling annualized volatility ---
    df = df.with_columns(
        (
            pl.col("log_returns").rolling_std(window_size=VOL_WINDOW).over("ticker")
            * (252.0**0.5)
        ).alias("volatility_20d"),
    )

    # --- Price / SMA ratios ---
    df = df.with_columns(
        (
            pl.col("close")
            / pl.col("close").rolling_mean(window_size=20).over("ticker")
        ).alias("close_sma20_ratio"),
        (
            pl.col("close")
            / pl.col("close").rolling_mean(window_size=50).over("ticker")
        ).alias("close_sma50_ratio"),
    )

    # --- Relative volume ---
    vol_f = pl.col("volume").cast(pl.Float64)
    df = df.with_columns(
        (vol_f / vol_f.rolling_mean(window_size=20).over("ticker")).alias(
            "volume_sma20_ratio"
        ),
    )

    return df


def build_ticker_mapping(
    tickers: list, save_path: str = "ticker_vocab.json"
) -> dict:
    """
    Build ticker -> integer ID mapping with <UNK>: 0 for OOV handling.
    Persists the mapping to *save_path* and returns it.
    """
    mapping: dict[str, int] = {"<UNK>": 0}
    for i, t in enumerate(sorted(set(tickers)), start=1):
        mapping[t] = i

    Path(save_path).write_text(json.dumps(mapping, indent=2))
    return mapping
