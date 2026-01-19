"""
data loader module
"""
import pandas as pd
import yfinance as yf
from functools import lru_cache
import time
import random
from ..utils.formatters import safe_float
from fastapi import HTTPException
from loguru import logger
import os
import requests
import io


def get_stock_metrics(ticker, start: str):
    # FMP provides 'quote' API for price, market cap, PE
    # 'key-metrics-ttm' API provides PS, PB, FCF, etc. TTM data

    base_url = "https://financialmodelingprep.com/stable/"
    api_key = os.getenv("FMP_API_KEY")
    try:
        # 1. get real-time price, market cap, PE
        quote_url = f"{base_url}/quote?symbol={ticker}&apikey={api_key}&startDate={start}"
        q_res = requests.get(quote_url).json()

        # 2. get key financial metrics (TTM version)
        metrics_url = f"{base_url}/key-metrics-ttm?symbol={ticker}&apikey={api_key}&startDate={start}"
        m_res = requests.get(metrics_url).json()

        if not q_res or not m_res:
            logger.warning(f"failed to get complete data for {ticker}")
            return None

        # Handle both list and dict responses
        if isinstance(q_res, list) and len(q_res) > 0:
            q = q_res[0]
        elif isinstance(q_res, dict):
            q = q_res
        else:
            return None

        if isinstance(m_res, list) and len(m_res) > 0:
            m = m_res[0]
        elif isinstance(m_res, dict):
            m = m_res
        else:
            return None

        # Ensure q and m are dicts before accessing
        if not isinstance(q, dict) or not isinstance(m, dict):
            logger.warning(
                f"Invalid response format for {ticker}: q is {type(q).__name__}, m is {type(m).__name__}")
            return None

        # map to your data structure
        return pd.DataFrame(data={
            "Price": [q.get("price")],
            "Shares": [q.get("sharesOutstanding")],
            "MarketCap": [q.get("marketCap")],
            # 估算营收
            "RevenueTTM": [m.get("revenuePerShareTTM") * q.get("sharesOutstanding") if m.get("revenuePerShareTTM") and q.get("sharesOutstanding") else None],
            "FCF": [m.get("freeCashFlowTTM")],
            "PE": [q.get("pe")],
            "PS": [m.get("priceToSalesRatioTTM")],
            "PB": [m.get("priceToBookRatioTTM")],
        })

    except Exception as e:
        logger.error(f"failed to get metrics for {ticker}: {e}")
        return None


def get_stock_data_from_fmp(ticker: str, start: str) -> pd.DataFrame:
    """
    get historical price data from FMP
    return historical price data with columns: Close, High, Low, Open, Volume
    """
    base_url = "https://financialmodelingprep.com/api/v3"
    stable_base_url = "https://financialmodelingprep.com/stable"
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return None

    end = pd.Timestamp.today(tz="UTC").date().isoformat()
    url = f"{base_url}/historical-price-full/{ticker}?from={start}&to={end}&apikey={api_key}"

    try:
        res = requests.get(url, timeout=10)

        if res.status_code in (401, 402, 403):
            payload = {}
        else:
            res.raise_for_status()
            payload = res.json()

        historical = payload.get("historical")
        if not historical:
            chart_url = f"{base_url}/historical-chart/1day/{ticker}?from={start}&to={end}&apikey={api_key}"
            chart_res = requests.get(chart_url, timeout=10)
            if chart_res.status_code in (401, 402, 403):
                if chart_res.status_code != 403:
                    chart_res.raise_for_status()
                historical = chart_res.json() if chart_res.ok else None

        if not historical:
            stable_url = (
                f"{stable_base_url}/historical-price-eod/full"
                f"?symbol={ticker}&from={start}&to={end}&apikey={api_key}"
            )
            stable_res = requests.get(stable_url, timeout=10)
            if stable_res.status_code in (401, 402, 403):
                if stable_res.status_code != 403:
                    stable_res.raise_for_status()
                if stable_res.ok:
                    stable_payload = stable_res.json()
                    if isinstance(stable_payload, dict):
                        historical = stable_payload.get(
                            "historical") or stable_payload.get("historicalStockList")
                    elif isinstance(stable_payload, list) and len(stable_payload) > 0:
                        historical = stable_payload
                    else:
                        historical = None
            else:
                stable_res.raise_for_status()
                if stable_res.ok:
                    stable_payload = stable_res.json()
                    if isinstance(stable_payload, dict):
                        historical = stable_payload.get(
                            "historical") or stable_payload.get("historicalStockList")
                    elif isinstance(stable_payload, list) and len(stable_payload) > 0:
                        historical = stable_payload
                    else:
                        historical = None
        if not historical:
            logger.warning(
                f"No historical data returned from FMP for {ticker}")
            return None

        df = pd.DataFrame(historical)
        if df.empty:
            return None

        # standardize column names and select required columns
        column_mapping = {
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=column_mapping)

        required_cols = ["Close", "High", "Low"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(
                f"Missing required columns in FMP data for {ticker}: {missing_cols}. Available columns: {df.columns.tolist()}"
            )
            return None

        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).set_index("Date")

        df = df.sort_index()

        # convert to numeric if possible
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        try:
            metrics_df = get_stock_metrics(ticker, start)
        except (NameError, AttributeError):
            metrics_df = None
        if metrics_df is not None and not metrics_df.empty:
            metrics_row = metrics_df.iloc[0].to_dict()
            for key, value in metrics_row.items():
                df[key] = value

        optional_cols = ["Open", "Volume"]
        cols_to_return = required_cols + \
            [col for col in optional_cols if col in df.columns]
        if metrics_df is not None and not metrics_df.empty:
            cols_to_return += [col for col in metrics_df.columns if col not in cols_to_return]
        return df[cols_to_return]
    except requests.RequestException as e:
        status_code = getattr(
            getattr(e, "response", None), "status_code", None)
        logger.error(
            f"Failed to get historical data from FMP for {ticker}: {type(e).__name__} status={status_code}")
        return None
    except Exception as e:
        logger.error(
            f"Failed to get historical data from FMP for {ticker}: {type(e).__name__}")
        return None


def get_stock_data_from_yfinance(ticker: str, start: str) -> pd.DataFrame:
    """
    get historical price data from yfinance
    return historical price data with columns: Close, High, Low, Open, Volume
    """
    tk = yf.Ticker(ticker)

    try:
        # get historical price data (this is the main data for technical analysis)
        hist = tk.history(start=start, end=None, interval="1d")

        if hist is None or hist.empty:
            # fallback: use yf.download to try to pull data
            hist = yf.download(
                ticker,
                start=start,
                end=None,
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )

        if hist is None or hist.empty:
            logger.warning(f"No historical data returned for {ticker}")
            return None

        # ensure there are enough trading days (at least 260 days, about 1 year)
        if len(hist) < 260:
            logger.warning(
                f"Insufficient historical data for {ticker}: {len(hist)} days")
            return None

        # yfinance returns column names usually in uppercase, ensure column names are correct
        # standardize column names (handle possible column name variations)
        column_mapping = {}
        for col in hist.columns:
            col_lower = col.lower()
            if col_lower == 'close':
                column_mapping[col] = 'Close'
            elif col_lower == 'high':
                column_mapping[col] = 'High'
            elif col_lower == 'low':
                column_mapping[col] = 'Low'
            elif col_lower == 'open':
                column_mapping[col] = 'Open'
            elif col_lower == 'volume':
                column_mapping[col] = 'Volume'

        if column_mapping:
            hist = hist.rename(columns=column_mapping)

        # ensure required columns exist
        required_cols = ['Close', 'High', 'Low']
        missing_cols = [
            col for col in required_cols if col not in hist.columns]
        if missing_cols:
            logger.error(
                f"Missing required columns in historical data for {ticker}: {missing_cols}. Available columns: {hist.columns.tolist()}")
            return None

        # return required columns, if there are other columns also return them
        optional_cols = ['Open', 'Volume']
        cols_to_return = required_cols + \
            [col for col in optional_cols if col in hist.columns]

        return hist[cols_to_return]

    except Exception as e:
        error_msg = str(e)
        # check if it is a 429 error
        if "429" in error_msg or "Too Many Requests" in error_msg:
            logger.warning(
                f"Rate limit hit for {ticker}, will retry with delay")
            raise Exception(f"Rate limit: {error_msg}")
        logger.error(
            f"Failed to get historical data from yfinance for {ticker}: {error_msg}")
        return None


def get_stock_data_from_stooq(ticker: str, start: str) -> pd.DataFrame:
    """
    get historical price data from Stooq (free fallback)
    return historical price data with columns: Close, High, Low, Open, Volume
    """
    # Stooq uses lowercase symbols with market suffix, e.g. goog.us
    symbol = ticker.lower()
    if "." not in symbol:
        symbol = f"{symbol}.us"

    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()

        df = pd.read_csv(io.StringIO(res.text))
        if df.empty or "Date" not in df.columns:
            return None

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).set_index("Date")
        df = df.sort_index()

        # filter by start date
        if start:
            df = df[df.index >= pd.to_datetime(start)]

        column_mapping = {
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Volume": "Volume",
        }
        df = df.rename(columns=column_mapping)

        required_cols = ["Close", "High", "Low"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return None

        # convert to numeric
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        optional_cols = ["Open", "Volume"]
        cols_to_return = required_cols + \
            [col for col in optional_cols if col in df.columns]
        return df[cols_to_return]
    except Exception:
        return None


@lru_cache(maxsize=50)
def load_price_cached(ticker: str, start: str, cache_buster: int = None, max_retries: int = 3) -> pd.DataFrame:
    """
    load historical price data (with cache, 15 minutes expiration)
    return historical price data with columns: Close, High, Low
    """
    # read configuration from environment variables
    max_retries = int(os.getenv("YFINANCE_MAX_RETRIES", max_retries))

    for attempt in range(max_retries):
        try:
            # increase delay when retrying
            if attempt > 0:
                delay = 1.5 ** attempt
                logger.info(
                    f"Retrying {ticker} after {delay:.1f}s delay (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)

            # prioritize getting historical price data from FMP, if failed fallback to yfinance
            df = get_stock_data_from_fmp(ticker, start)
            if df is None or df.empty:
                logger.warning(
                    f"Failed to get historical price data from FMP for {ticker}, trying yinance")
                df = get_stock_data_from_yfinance(ticker, start)

            if df is None or df.empty:
                logger.warning(
                    f"Failed to get historical price data from yfinance for {ticker}, trying stooq")
                df = get_stock_data_from_stooq(ticker, start)

            # verify data completeness
            if df is None or df.empty:
                logger.warning(
                    f"No data returned for {ticker} on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"No data available for {ticker}. Please try again later."
                    )

            # check required columns
            if "Close" not in df.columns:
                logger.error(
                    f"Missing 'Close' column for {ticker}. Columns: {df.columns.tolist()}")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Invalid data format for {ticker}. Missing required columns."
                    )

            # check data volume (at least 260 trading days, about 1 year)
            if len(df) < 260:
                logger.warning(
                    f"Insufficient data for {ticker}: {len(df)} rows (need at least 260)")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Insufficient historical data for {ticker}. Need at least 260 trading days."
                    )

            logger.info(
                f"Loaded price data for {ticker} from {start} to {pd.Timestamp.today(tz='UTC').date().isoformat()} after {attempt + 1} attempts ({len(df)} rows)")
            return df

        except HTTPException:
            # rethrow HTTPException
            raise
        except Exception as e:
            error_msg = str(e)
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} failed for {ticker}: {error_msg}")

            # if it is the last attempt, throw an exception
            if attempt == max_retries - 1:
                logger.error(
                    f"Failed to load {ticker} after {max_retries} attempts")
                raise HTTPException(
                    status_code=503,
                    detail=f"Yahoo Finance API rate limit or temporarily unavailable. Please try again later. Error: {error_msg}"
                )

            # if it is a rate limit error, increase delay time
            if "429" in error_msg or "Too Many Requests" in error_msg or "Rate limit" in error_msg:
                delay = random.uniform(10, 20)  # wait longer for 429 error
                logger.warning(
                    f"Rate limit detected for {ticker}, waiting {delay:.1f}s before retry")
                time.sleep(delay)
            else:
                # other errors, use exponential backoff
                time.sleep(random.uniform(2, 5))


def load_price(ticker: str, start: str) -> pd.DataFrame:
    """load price data (with cache control)"""
    cache_buster = int(time.time() / 900)  # 15 minutes
    return load_price_cached(ticker, start, cache_buster)
