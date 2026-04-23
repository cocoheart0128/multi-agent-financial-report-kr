"""
Market Analyst Agent（시장 분석 Agent）
职責：분석 추세, 위험 신호 식별, 기술 지표 계산
在Pipeline中串行执行，依赖 Data Collector 和 Sentiment Agent 的输出
"""

import logging
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential

from models.report_schema import (
    CollectedData,
    MarketAnalysis,
    Recommendation,
    RiskFactor,
    RiskLevel,
    SentimentAnalysis,
    TechnicalIndicator,
)

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """당신은 경험많은 금융 시장 분석가입니다. 다음 데이터를 기반으로
종합적인 시장 분석을 제공하세요.

회사: {company_name} ({ticker})
섹터: {sector}

재무 지표:
- 시가 총액: {market_cap}
- P/E 비율: {pe_ratio}
- P/B 비율: {pb_ratio}
- ROE: {roe}%
- 부채/자본 비율: {debt_to_equity}
- 매출: {revenue}
- 순이익: {net_income}
- 자유 현금 흐름: {free_cash_flow}

최근 가격 추세 (최근 5일 종가):
{price_trend}

감정 분석:
- 전체: {sentiment}
- 점수: {sentiment_score}
- 주요 주제: {key_topics}

이 정확한 JSON 형식으로 분석을 제공하세요:
{{
    "trend_direction": "uptrend|downtrend|sideways",
    "recommendation": "strong_buy|buy|hold|sell|strong_sell",
    "risk_level": "low|medium|high|critical",
    "price_target": <float or null>,
    "support_level": <float or null>,
    "resistance_level": <float or null>,
    "analysis_summary": "상세한 한국어 분석 요약, 추세 판단, 위험 평가, 투자 조언 포함...",
    "risk_factors": [
        {{"category": "market|credit|operational|regulatory", "description": "...", "severity": "low|medium|high|critical", "mitigation": "..."}}
    ],
    "technical_signals": [
        {{"name": "지표명", "signal": "bullish|bearish|neutral", "description": "..."}}
    ]
}}
"""


class MarketAnalystAgent:
    """
    市场分析Agent - 综合分析市场数据和舆情，给出投资建议

    输入: CollectedData + SentimentAnalysis
    输出: MarketAnalysis

    面试考点:
    - 为什么分析Agent要等数据和舆情都完成？
      → 分析需要完整信息，不完整数据会导致偏差
    - 如何保证分析的一致性和准确性？
      → 结构化prompt + 温度参数低 + Pydantic schema验证
    """

    def __init__(self):
        self.name = "MarketAnalystAgent"
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"),
            temperature=0.2,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def execute(
        self,
        collected_data: CollectedData,
        sentiment: SentimentAnalysis,
    ) -> MarketAnalysis:
        """执行市场分析"""
        logger.info("[%s] Starting analysis for %s", self.name, collected_data.ticker)

        price_trend = self._format_price_trend(collected_data)
        metrics = collected_data.financial_metrics

        prompt = ANALYSIS_PROMPT.format(
            company_name=collected_data.company_info.name,
            ticker=collected_data.ticker,
            sector=collected_data.company_info.sector,
            market_cap=_format_number(metrics.market_cap),
            pe_ratio=metrics.pe_ratio or "N/A",
            pb_ratio=metrics.pb_ratio or "N/A",
            roe=metrics.roe or "N/A",
            debt_to_equity=metrics.debt_to_equity or "N/A",
            revenue=_format_number(metrics.revenue),
            net_income=_format_number(metrics.net_income),
            free_cash_flow=_format_number(metrics.free_cash_flow),
            price_trend=price_trend,
            sentiment=sentiment.overall_sentiment.value,
            sentiment_score=sentiment.sentiment_score,
            key_topics=", ".join(sentiment.key_topics),
        )

        llm_result = await self._analyze_with_llm(prompt)

        technical_indicators = self._compute_technical_indicators(collected_data)
        technical_indicators.extend(
            TechnicalIndicator(
                name=sig["name"],
                value=0.0,
                signal=sig["signal"],
                description=sig.get("description", ""),
            )
            for sig in llm_result.get("technical_signals", [])
        )

        risk_factors = [
            RiskFactor(
                category=rf["category"],
                description=rf["description"],
                severity=RiskLevel(rf["severity"]),
                mitigation=rf.get("mitigation", ""),
            )
            for rf in llm_result.get("risk_factors", [])
        ]

        result = MarketAnalysis(
            ticker=collected_data.ticker,
            trend_direction=llm_result.get("trend_direction", "sideways"),
            technical_indicators=technical_indicators,
            risk_factors=risk_factors,
            overall_risk_level=RiskLevel(llm_result.get("risk_level", "medium")),
            price_target=llm_result.get("price_target"),
            support_level=llm_result.get("support_level"),
            resistance_level=llm_result.get("resistance_level"),
            recommendation=Recommendation(llm_result.get("recommendation", "hold")),
            analysis_summary=llm_result.get("analysis_summary", ""),
        )

        logger.info(
            "[%s] Analysis complete: %s → %s (risk: %s)",
            self.name,
            collected_data.ticker,
            result.recommendation.value,
            result.overall_risk_level.value,
        )
        return result

    def _compute_technical_indicators(self, data: CollectedData) -> list[TechnicalIndicator]:
        """计算基础技术指标（纯数学计算，不依赖LLM）"""
        indicators = []
        prices = data.recent_prices

        if len(prices) < 5:
            return indicators

        closes = [p.close for p in prices]

        if len(closes) >= 20:
            ma20 = sum(closes[-20:]) / 20
            current = closes[-1]
            signal = "bullish" if current > ma20 else "bearish"
            indicators.append(
                TechnicalIndicator(
                    name="MA20",
                    value=round(ma20, 2),
                    signal=signal,
                    description=f"20日均线: {ma20:.2f}, 当前价: {current:.2f}",
                )
            )

        if len(closes) >= 14:
            rsi = self._calculate_rsi(closes, 14)
            if rsi > 70:
                rsi_signal = "bearish"
            elif rsi < 30:
                rsi_signal = "bullish"
            else:
                rsi_signal = "neutral"
            indicators.append(
                TechnicalIndicator(
                    name="RSI14",
                    value=round(rsi, 2),
                    signal=rsi_signal,
                    description=f"14日RSI: {rsi:.2f}",
                )
            )

        if len(closes) >= 2:
            volatility = self._calculate_volatility(closes[-20:] if len(closes) >= 20 else closes)
            vol_signal = "bearish" if volatility > 3.0 else "neutral"
            indicators.append(
                TechnicalIndicator(
                    name="Volatility",
                    value=round(volatility, 2),
                    signal=vol_signal,
                    description=f"波动率: {volatility:.2f}%",
                )
            )

        return indicators

    @staticmethod
    def _calculate_rsi(prices: list[float], period: int = 14) -> float:
        """计算RSI指标"""
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        recent = deltas[-period:]
        gains = [d for d in recent if d > 0]
        losses = [-d for d in recent if d < 0]

        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0.001

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calculate_volatility(prices: list[float]) -> float:
        """计算价格波动率（日收益率标准差）"""
        if len(prices) < 2:
            return 0.0
        returns = [(prices[i] / prices[i - 1]) - 1 for i in range(1, len(prices))]
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        return (variance ** 0.5) * 100

    def _format_price_trend(self, data: CollectedData) -> str:
        """格式化最近价格趋势"""
        if not data.recent_prices:
            return "No price data available"
        recent = data.recent_prices[-5:]
        return "\n".join(
            f"  {p.date}: Close={p.close}, Volume={p.volume:,}" for p in recent
        )

    async def _analyze_with_llm(self, prompt: str) -> dict:
        """使用LLM进行综合分析"""
        try:
            response = await self.llm.ainvoke(prompt)
            import json

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())
        except Exception as e:
            logger.warning("LLM analysis failed: %s, using fallback", e)
            return {
                "trend_direction": "sideways",
                "recommendation": "hold",
                "risk_level": "medium",
                "analysis_summary": "分析暂不可用，建议人工审核。",
                "risk_factors": [],
                "technical_signals": [],
            }


def _format_number(value) -> str:
    """格式化大数字"""
    if value is None:
        return "N/A"
    try:
        v = float(value)
        if abs(v) >= 1e12:
            return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:
            return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:.2f}M"
        return f"${v:,.2f}"
    except (TypeError, ValueError):
        return "N/A"
