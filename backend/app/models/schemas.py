"""
Pydantic 数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal


class AnalysisRequest(BaseModel):
    """分析请求模型"""
    ticker: str = Field(..., description="股票代码", example="MSFT")
    years: int = Field(10, ge=2, le=15, description="历史回看长度（年）")
    mode: Literal["conservative", "standard", "aggressive"] = Field(
        "standard", 
        description="投资风格"
    )
    ##


class SignalResponse(BaseModel):
    """信号响应模型"""
    Signal: str
    Last: float
    RSI: float
    Pct3Y: Optional[float]
    Pct5Y: Optional[float]
    A_pos: bool
    B_rsi: bool
    C_turn: bool


class RiskResponse(BaseModel):
    """风险响应模型"""
    Risk: str
    RiskScore: int
    TrendUp: bool
    MA50: Optional[float]
    MA200: Optional[float]
    Vol: Optional[float]
    DD1Y: Optional[float]
    Last: float


class ZonesResponse(BaseModel):
    """买入区间响应模型"""
    ATR14: Optional[float]
    Last: float
    Conservative: tuple[float, float]
    Neutral: tuple[float, float]
    Aggressive: tuple[float, float]


class AddLevelsResponse(BaseModel):
    """加仓位置响应模型"""
    FirstAdd: float
    PullbackAdd: float
    ValuePocketAdd: Optional[float]
    ValuePocketRule: Optional[str]


class FundamentalsResponse(BaseModel):
    """基本面响应模型"""
    Price: Optional[float]
    Shares: Optional[float]
    MarketCap: Optional[float]
    RevenueTTM: Optional[float]
    FCF: Optional[float]
    PE: Optional[float]
    PS: Optional[float]
    PB: Optional[float]


class FairValueResponse(BaseModel):
    """公允价值响应模型"""
    Method: str
    FairLow: Optional[float]
    FairMid: Optional[float]
    FairHigh: Optional[float]


class AnalysisResponse(BaseModel):
    """完整分析响应模型"""
    signal: SignalResponse
    risk: RiskResponse
    zones: ZonesResponse
    fundamentals: FundamentalsResponse
    fair_value: FairValueResponse
    add_levels: AddLevelsResponse


class OptimizeRequest(BaseModel):
    tickers: list[str] = Field(
        ...,
        min_length=2,
        description="List of stock tickers to optimize",
        examples=[["AAPL", "MSFT", "GOOG", "AMZN"]],
    )
    lookback_years: int = Field(
        3, ge=1, le=10, description="Years of historical data to use"
    )
    risk_free_rate: float = Field(
        0.04, ge=0.0, le=0.2, description="Annualized risk-free rate"
    )
    vol_penalty: float = Field(
        0.5,
        ge=0.0,
        le=5.0,
        description="Volatility penalty strength — higher values bias toward low-vol blue-chips",
    )


class OptimizeResponse(BaseModel):
    weights: dict[str, float] = Field(
        ..., description="Optimal weight per ticker"
    )
    expected_return: float = Field(
        ..., description="Annualized expected portfolio return"
    )
    volatility: float = Field(
        ..., description="Annualized portfolio volatility"
    )
    sharpe_ratio: float = Field(
        ..., description="Portfolio Sharpe ratio"
    )

