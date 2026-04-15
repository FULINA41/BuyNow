"""
Panel data downloader for the Global Alpha Model.
Downloads daily OHLCV via alpaca-py, stacks into long format,
computes features and forward-return labels, saves panel_data.parquet.

Run from the backend/ directory:
    python -m train.data_loader
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
from app.ml.features import calculate_features_polars, build_ticker_mapping  # noqa: E402


LOOKBACK_YEARS = 5
FORWARD_HORIZONS = [1, 2, 3, 5]
CHUNK_SIZE = 10

import io
import urllib.request

import pandas as pd


def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    html = urllib.request.urlopen(req).read().decode("utf-8")
    table = pd.read_html(io.StringIO(html))
    df = table[0]
    tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
    return tickers

# DEFAULT_UNIVERSE = get_sp500_tickers()
DEFAULT_UNIVERSE = get_sp500_tickers()


def download_universe(
    tickers: list[str] | None = None,
    lookback_years: int = LOOKBACK_YEARS,
    chunk_size: int = CHUNK_SIZE,
) -> pl.DataFrame:
    """Download daily bars for the ticker universe via Alpaca.

    Tickers are requested in batches of *chunk_size* to stay within
    Alpaca free-tier limits.  Data is extracted by iterating the raw
    ``.data`` dict (bypassing the slow Pandas MultiIndex path).

    Args:
        tickers: Symbols to download. Defaults to DEFAULT_UNIVERSE.
        lookback_years: Years of history to fetch.
        chunk_size: Max symbols per API request.

    Returns:
        Polars DataFrame sorted by (ticker, date) with columns
        [ticker, date, open, high, low, close, volume].

    Raises:
        RuntimeError: If no data could be downloaded for any ticker.
    """
    tickers = tickers or DEFAULT_UNIVERSE

    client = StockHistoricalDataClient(
        api_key=os.getenv("ALPACA_API_KEY_ID"),
        secret_key=os.getenv("ALPACA_API_SECRET_KEY"),
    )

    end = datetime.now() - timedelta(minutes=16)
    start = end - timedelta(days=lookback_years * 365)

    chunks = [
        tickers[i : i + chunk_size]
        for i in range(0, len(tickers), chunk_size)
    ]

    all_rows: list[dict] = []

    for idx, chunk in enumerate(chunks, 1):
        print(f"  Chunk {idx}/{len(chunks)}: {len(chunk)} tickers …")

        try:
            request = StockBarsRequest(
                symbol_or_symbols=chunk,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
            )
            barset = client.get_stock_bars(request)
        except Exception as exc:
            print(f"  ⚠ Chunk {idx} failed: {exc}. Skipping.")
            continue

        if not barset.data:
            print(f"  ⚠ Chunk {idx} returned empty data. Skipping.")
            continue

        for symbol, bars in barset.data.items():
            for bar in bars:
                all_rows.append(
                    {
                        "ticker": bar.symbol,
                        "date": bar.timestamp.date(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                    }
                )

        print(f"    ✓ {len(all_rows):,} cumulative rows")

    if not all_rows:
        raise RuntimeError(
            "No data downloaded for any ticker. "
            "Check Alpaca credentials and network connectivity."
        )

    df = pl.DataFrame(
        all_rows,
        schema={
            "ticker": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
        },
    )

    return df.sort("ticker", "date")


def add_forward_returns(
    df: pl.DataFrame,
    horizons: list[int] | None = None,
) -> pl.DataFrame:
    """
    Add forward-return label columns.
    fwd_ret_{n}d = (close[t+n] - close[t]) / close[t]
    """
    horizons = horizons or FORWARD_HORIZONS
    df = df.sort("ticker", "date")

    return df.with_columns(
        [
            (
                (pl.col("close").shift(-h).over("ticker") - pl.col("close"))
                / pl.col("close")
            ).alias(f"fwd_ret_{h}d")
            for h in horizons
        ]
    )


def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")

    print(f"Downloading {len(DEFAULT_UNIVERSE)} tickers, {LOOKBACK_YEARS}y lookback …")
    df = download_universe()
    print(f"  → {len(df):,} rows, {df['ticker'].n_unique()} tickers")

    print("Calculating features …")
    df = calculate_features_polars(df)

    print("Adding forward-return labels …")
    df = add_forward_returns(df)

    df = df.drop_nulls()
    print(f"  → {len(df):,} rows after dropping nulls")

    print("Building ticker vocabulary …")
    tickers = df["ticker"].unique().to_list()
    vocab_path = str(SCRIPT_DIR / "ticker_vocab.json")
    vocab = build_ticker_mapping(tickers, save_path=vocab_path)
    print(f"  → Vocab size: {len(vocab)} (including <UNK>)")

    df = df.with_columns(
        pl.col("ticker")
        .map_elements(lambda t: vocab.get(t, 0), return_dtype=pl.Int64)
        .alias("ticker_id"),
    )

    output_path = SCRIPT_DIR / "panel_data.parquet"
    df.write_parquet(str(output_path))
    print(f"Saved → {output_path} ({len(df):,} rows)")


if __name__ == "__main__":
    main()
