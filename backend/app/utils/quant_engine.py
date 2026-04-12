"""
Portfolio optimization engine using Alpaca market data,
vectorized Pandas/NumPy returns analysis, and SciPy-based
mean-variance (Max Sharpe) optimization.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests
from loguru import logger
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

ALPACA_DATA_BASE = "https://data.alpaca.markets/v2/stocks"
TRADING_DAYS_PER_YEAR = 252


class PortfolioOptimizer:

    def __init__(self):
        self._api_key = os.getenv("ALPACA_API_KEY_ID", "")
        self._api_secret = os.getenv("ALPACA_API_SECRET_KEY", "")
        if not self._api_key or not self._api_secret:
            raise ValueError(
                "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY must be set in environment")

    def _alpaca_headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    def _fetch_ticker_batch(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, pd.Series]:
        """
        Fetch daily adjusted close prices for a batch of tickers using the
        multi-symbol endpoint ``GET /v2/stocks/bars``.

        Handles pagination — the API sorts results by symbol first, then
        timestamp, so a single page may only contain bars for one symbol
        when the limit is reached.
        """
        url = f"{ALPACA_DATA_BASE}/bars"
        params = {
            "symbols": ",".join(tickers),
            "timeframe": "1Day",
            "start": start_date,
            "end": end_date,
            "adjustment": "all",
            "limit": 10000,
            "feed": "sip",
            "sort": "asc",
        }

        accumulated: Dict[str, list] = {t: [] for t in tickers}
        page_token: Optional[str] = None

        while True:
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(
                url, headers=self._alpaca_headers(), params=params, timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()

            bars_by_symbol: dict = payload.get("bars") or {}
            for symbol, bars in bars_by_symbol.items():
                accumulated.setdefault(symbol, []).extend(bars)

            page_token = payload.get("next_page_token")
            if not page_token:
                break

        # convert the bars to close prices
        results: Dict[str, pd.Series] = {}
        for symbol, bars in accumulated.items():
            if not bars:
                logger.warning(f"No Alpaca bars returned for {symbol}")
                continue
            df = pd.DataFrame(bars)
            df["t"] = pd.to_datetime(df["t"])
            df = df.set_index("t").sort_index()
            results[symbol] = df["c"].rename(symbol)

        return results

    def fetch_data_concurrently(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        max_workers: int = 4,
        chunk_size: int = 10,
    ) -> pd.DataFrame:
        """
        Fetch adjusted close prices for multiple tickers concurrently.

        Splits *tickers* into chunks of *chunk_size* and fetches each chunk
        in parallel via ``ThreadPoolExecutor`` against the multi-symbol
        ``/v2/stocks/bars`` endpoint.

        Returns a DataFrame indexed by date with one column per ticker.
        """
        chunks = [
            tickers[i: i + chunk_size]
            for i in range(0, len(tickers), chunk_size)
        ]

        all_series: Dict[str, pd.Series] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(
                    self._fetch_ticker_batch, chunk, start_date, end_date,
                ): chunk
                for chunk in chunks
            }
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                try:
                    batch_results = future.result()
                    all_series.update(batch_results)
                except Exception as exc:
                    logger.error(
                        f"Failed to fetch chunk {chunk}: {exc}"
                    )

        if not all_series:
            raise ValueError("No data fetched for any ticker")

        df = pd.DataFrame(all_series)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index().dropna()
        logger.info(f"Fetched {len(df)} trading days for {list(df.columns)}")
        return df

    @staticmethod
    def calculate_returns_and_cov(
        prices: pd.DataFrame,
    ) -> tuple[pd.Series, pd.DataFrame]:
        """
        Compute annualized expected returns (mean daily log-return * 252)
        and the annualized covariance matrix from a prices DataFrame.
        """
        log_returns = np.log(prices / prices.shift(1)).dropna()
        expected_returns = log_returns.mean() * TRADING_DAYS_PER_YEAR
        # cov_matrix = log_returns.cov() * TRADING_DAYS_PER_YEAR
        lw = LedoitWolf().fit(log_returns.values)
        cov_matrix = pd.DataFrame(
            lw.covariance_ * TRADING_DAYS_PER_YEAR,
            index=log_returns.columns,
            columns=log_returns.columns,
        )
        return expected_returns, cov_matrix

    @staticmethod
    def optimize_max_sharpe(
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        risk_free_rate: float = 0.04,
        vol_penalty: float = 0.5,
    ) -> Dict[str, float]:
        """
        Find the portfolio weights that maximise the Sharpe ratio.

        Uses SLSQP with constraints:
          - weights sum to 1
          - each weight in [0, 1]  (long-only)

        Penalty terms in the objective:
          - L2 regularisation to avoid extreme concentration
          - Per-asset volatility penalty: vol_penalty * Σ(wᵢ · σᵢ),
            higher vol_penalty → stronger bias toward low-vol blue-chips
        """
        n = len(expected_returns)
        init_weights = np.full(n, 1.0 / n)

        l2_lambda = 0.1
        asset_vols = np.sqrt(np.diag(cov_matrix.values))

        def neg_sharpe(weights: np.ndarray) -> float:
            port_return = weights @ expected_returns.values
            port_vol = np.sqrt(weights @ cov_matrix.values @ weights)
            if port_vol == 0:
                return 1e6
            sharpe = (port_return - risk_free_rate) / port_vol
            penalty = l2_lambda * np.sum(weights ** 2)
            vol_drag = vol_penalty * (weights @ asset_vols)
            return -sharpe + penalty + vol_drag

        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        bounds = tuple((0.05, 1.0) for _ in range(n))

        result = minimize(
            neg_sharpe,
            init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        if not result.success:
            logger.warning(f"Optimizer did not converge: {result.message}")

        optimal_weights = result.x
        tickers = expected_returns.index.tolist()
        weight_dict = {
            ticker: round(float(w), 6)
            for ticker, w in zip(tickers, optimal_weights)
        }

        port_ret = optimal_weights @ expected_returns.values
        port_vol = np.sqrt(
            optimal_weights @ cov_matrix.values @ optimal_weights)
        sharpe = (port_ret - risk_free_rate) / \
            port_vol if port_vol > 0 else 0.0

        logger.info(
            f"Optimal portfolio — return: {port_ret:.4f}, vol: {port_vol:.4f}, sharpe: {sharpe:.4f}"
        )

        return {
            "weights": weight_dict,
            "expected_annual_return": round(float(port_ret), 6),
            "annual_volatility": round(float(port_vol), 6),
            "sharpe_ratio": round(float(sharpe), 6),
        }
