"""
分析 API 路由
"""
from loguru import logger
from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse
import pandas as pd
from ..models.schemas import AnalysisRequest, AnalysisResponse, SignalResponse, RiskResponse, ZonesResponse, FundamentalsResponse, FairValueResponse, AddLevelsResponse
from ..services.data_loader import load_price
from ..services.signals import signal_abc
from ..services.risk import risk_level
from ..services.zones import buy_zones, add_levels
from ..services.fundamentals import get_fundamentals, rough_fair_value_range
from ..core.logging_config import setup_logging
from ..services.LLM import analyze_stock_fundamentals_llm
import json
setup_logging()
logger.add("logs/analysis.log", backtrace=True, diagnose=True)


router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_stock(request: AnalysisRequest):

    """
    analyze stock: generate signal, risk, buy zones, etc.
    """
    try:
        # calculate start date
        start = (pd.Timestamp.today(tz="UTC") -
                 pd.Timedelta(days=365 * request.years)).date().isoformat()

        # load price data
        df = load_price(request.ticker, start)

        # check if data is available
        if (
            df is None
            or not hasattr(df, "__getitem__")
            or "Close" not in df
            or df["Close"] is None
            or (hasattr(df["Close"], "__len__") and len(df["Close"]) < 260)
        ):
            logger.error(
                f"Data not available for {request.ticker}: {df.head() if df is not None else 'No data'}")
            raise HTTPException(
                status_code=400,
                detail="data not enough or failed to load"
            )

        # core calculation
        sig = signal_abc(df)
        risk = risk_level(df)
        zones = buy_zones(df)

        # fundamentals analysis
        f = get_fundamentals(request.ticker)
        fair = rough_fair_value_range(f)

        # add levels
        adds = add_levels(sig["Last"], zones, fair)

        # build response
        return AnalysisResponse(
            signal=SignalResponse(**sig),
            risk=RiskResponse(**risk),
            zones=ZonesResponse(**zones),
            fundamentals=FundamentalsResponse(**f),
            fair_value=FairValueResponse(**fair),
            add_levels=AddLevelsResponse(**adds)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"error during analysis: {str(e)}"
        )

@router.post('/analyze/LLM')
async def analyze_stock_llm(request: AnalysisRequest):
    # 1. get async generator
    # 确保 analyze_stock_fundamentals_llm 内部使用了 async for 和 await client.aio
    gen = analyze_stock_fundamentals_llm(request)

    # 2. convert the sting to SSE
    async def event_generator():
        try:
            async for chunk in gen:
                # 构造前端 fetchLLMAnalysis 函数预期的 JSON 结构
                # 这样前端 JSON.parse(data) 才能拿到 .content
                data = json.dumps({"content": chunk})
                yield f"data: {data}\n\n"
            
            # 告诉前端传输彻底结束
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    # 3. 返回响应，添加必要的 Header 防止缓存
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 极其重要：告诉 Nginx 不要缓存流
        }
    )