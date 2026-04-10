"""
Portfolio optimization API router
"""
from fastapi import APIRouter, HTTPException
from loguru import logger
import pandas as pd

from ..models.schemas import OptimizeRequest, OptimizeResponse
from ..utils.quant_engine import PortfolioOptimizer

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_portfolio(request: OptimizeRequest):
    """
    Accept a list of tickers and a lookback window, then return
    the Max-Sharpe optimal weight allocation.
    """
    end_date = (
        pd.Timestamp.today(tz="UTC") - pd.Timedelta(minutes=16)
    ).isoformat()
    start_date = (
        pd.Timestamp.today(
            tz="UTC") - pd.DateOffset(years=request.lookback_years)
    ).date().isoformat()

    try:
        optimizer = PortfolioOptimizer()

        prices = optimizer.fetch_data_concurrently(
            tickers=request.tickers,
            start_date=start_date,
            end_date=end_date,
        )

        if prices.shape[1] < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Need at least 2 tickers with data. Only got: {list(prices.columns)}",
            )

        expected_returns, cov_matrix = optimizer.calculate_returns_and_cov(
            prices)
        result = optimizer.optimize_max_sharpe(
            expected_returns, cov_matrix, risk_free_rate=request.risk_free_rate,
        )

        return OptimizeResponse(
            weights=result["weights"],
            expected_return=result["expected_annual_return"],
            volatility=result["annual_volatility"],
            sharpe_ratio=result["sharpe_ratio"],
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Portfolio optimization failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Optimization failed: {str(e)}",
        )
