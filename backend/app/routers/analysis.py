"""
分析 API 路由
"""
from fastapi import APIRouter, HTTPException
import pandas as pd
from ..models.schemas import AnalysisRequest, AnalysisResponse, SignalResponse, RiskResponse, ZonesResponse, FundamentalsResponse, FairValueResponse, AddLevelsResponse
from ..services.data_loader import load_price
from ..services.signals import signal_abc
from ..services.risk import risk_level
from ..services.zones import buy_zones, add_levels
from ..services.fundamentals import get_fundamentals, rough_fair_value_range

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_stock(request: AnalysisRequest):
    """
    分析股票：生成信号、风险、买入区间等
    """
    try:
        # 计算开始日期
        start = (pd.Timestamp.today(tz="UTC") - pd.Timedelta(days=365 * request.years)).date().isoformat()

        # 加载价格数据
        df = load_price(request.ticker, start)

        if df is None or df.empty or "Close" not in df.columns or len(df) < 260:
            raise HTTPException(
                status_code=400,
                detail="数据不足或拉取失败（可能 ticker 错误、停牌、或历史太短）"
            )

        # 核心计算
        sig = signal_abc(df)
        risk = risk_level(df)
        zones = buy_zones(df)

        # 基本面分析
        f = get_fundamentals(request.ticker)
        fair = rough_fair_value_range(f)

        # 加仓位置
        adds = add_levels(sig["Last"], zones, fair)

        # 构建响应
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
            detail=f"分析过程中出错: {str(e)}"
        )
