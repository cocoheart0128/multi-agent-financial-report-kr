"""
结构化报告数据模型 - 使用Pydantic v2强制JSON Schema
所有Agent的输入输出都通过这些模型来约束，确保数据一致性
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Recommendation(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class SentimentScore(str, Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


# ==================== Agent Input Schemas ====================

class StockQuery(BaseModel):
    """用户输入：股票查询请求"""
    ticker: str = Field(..., description="股票代码，如 AAPL, TSLA, MSFT")
    period: str = Field(default="1y", description="分析周期: 1mo, 3mo, 6mo, 1y, 2y")
    language: str = Field(default="zh", description="报告语言: zh(中文), ko(韓文), en(英文), ja(日本語)")


# ==================== Data Collector Output ====================

class StockPrice(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class FinancialMetrics(BaseModel):
    market_cap: Optional[float] = Field(None, description="市值")
    pe_ratio: Optional[float] = Field(None, description="市盈率")
    pb_ratio: Optional[float] = Field(None, description="市净率")
    dividend_yield: Optional[float] = Field(None, description="股息率 %")
    revenue: Optional[float] = Field(None, description="营收")
    net_income: Optional[float] = Field(None, description="净利润")
    debt_to_equity: Optional[float] = Field(None, description="资产负债率")
    roe: Optional[float] = Field(None, description="净资产收益率 %")
    current_ratio: Optional[float] = Field(None, description="流动比率")
    free_cash_flow: Optional[float] = Field(None, description="自由现金流")


# class CompanyInfo(BaseModel):
#     name: str = Field(..., description="公司名称")
#     sector: str = Field(default="Unknown", description="行业板块")
#     industry: str = Field(default="Unknown", description="细分行业")
#     description: str = Field(default="", description="公司简介")
#     website: str = Field(default="", description="官网")
#     employees: Optional[int] = Field(None, description="员工数")

class CompanyInfo(BaseModel):
    name: str = Field(..., description="공司名称")
    ticker: str = Field(default="Unknown", description="주식번호")
    crno: str = Field(default="Unknown", description="법인등록번호")
    established_date: str = Field(default="", description="기업의설립일자")
    website: str = Field(default="", description="官网")
    employees: Optional[int] = Field(None, description="员工数")
    sector: str = Field(default="Unknown", description="업종")
    industry: str = Field(default="Unknown", description="세부업종")
    description: str = Field(default="", description="기업설명")


class CollectedData(BaseModel):
    """Data Collector Agent 的输出"""
    ticker: str
    company_info: CompanyInfo
    financial_metrics: FinancialMetrics
    recent_prices: list[StockPrice] = Field(default_factory=list)
    sec_filings: list[str] = Field(default_factory=list, description="最近SEC文件摘要")
    data_sources: list[str] = Field(default_factory=list, description="数据来源列表")
    collected_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ==================== Sentiment Agent Output ====================

class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: str
    sentiment: SentimentScore
    summary: str = ""


class SentimentAnalysis(BaseModel):
    """Sentiment Agent 的输出"""
    ticker: str
    overall_sentiment: SentimentScore
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="情感分数 -1到1")
    news_items: list[NewsItem] = Field(default_factory=list)
    key_topics: list[str] = Field(default_factory=list, description="热门话题")
    social_buzz_score: float = Field(default=0.0, description="社交热度分数 0-100")
    analysis_summary: str = Field(default="", description="舆情分析摘要")
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ==================== Market Analyst Output ====================

class TechnicalIndicator(BaseModel):
    name: str = Field(..., description="指标名称，如 MA50, RSI, MACD")
    value: float
    signal: str = Field(..., description="信号: bullish, bearish, neutral")
    description: str = ""


class RiskFactor(BaseModel):
    category: str = Field(..., description="风险类别: market, credit, operational, regulatory")
    description: str
    severity: RiskLevel
    mitigation: str = Field(default="", description="缓解建议")


class MarketAnalysis(BaseModel):
    """Market Analyst Agent 的输出"""
    ticker: str
    trend_direction: str = Field(..., description="趋势方向: uptrend, downtrend, sideways")
    technical_indicators: list[TechnicalIndicator] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    overall_risk_level: RiskLevel
    price_target: Optional[float] = Field(None, description="目标价格")
    support_level: Optional[float] = Field(None, description="支撑位")
    resistance_level: Optional[float] = Field(None, description="阻力位")
    recommendation: Recommendation
    analysis_summary: str = ""
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ==================== Report Writer Output ====================

class ReportSection(BaseModel):
    title: str
    content: str
    order: int


class InvestmentReport(BaseModel):
    """Report Writer Agent 的输出 - 完整的投资研究报告"""
    title: str
    ticker: str
    executive_summary: str = Field(..., description="执行摘要")
    company_overview: str
    financial_analysis: str
    technical_analysis: str
    sentiment_overview: str
    risk_assessment: str
    investment_recommendation: str
    recommendation: Recommendation
    price_target: Optional[float] = None
    additional_sections: list[ReportSection] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ==================== Compliance Agent Output ====================

class ComplianceIssue(BaseModel):
    severity: str = Field(..., description="严重程度: critical, warning, info")
    category: str = Field(..., description="类别: disclaimer, data_citation, regulatory, bias")
    description: str
    location: str = Field(default="", description="问题位置")
    suggestion: str = Field(default="", description="修改建议")


class ComplianceReport(BaseModel):
    """Compliance Agent 的输出"""
    is_compliant: bool
    issues: list[ComplianceIssue] = Field(default_factory=list)
    disclaimer_present: bool = Field(default=False)
    data_citations_valid: bool = Field(default=False)
    regulatory_compliant: bool = Field(default=False)
    bias_check_passed: bool = Field(default=False)
    compliance_score: float = Field(..., ge=0.0, le=100.0, description="合规分数 0-100")
    reviewed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ==================== Final Output ====================

class FinalReport(BaseModel):
    """最终输出：包含报告+合规审查结果"""
    report: InvestmentReport
    compliance: ComplianceReport
    collected_data: CollectedData
    sentiment: SentimentAnalysis
    market_analysis: MarketAnalysis
    metadata: dict = Field(default_factory=dict)
