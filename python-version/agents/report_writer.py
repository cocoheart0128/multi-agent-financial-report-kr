"""
Report Writer Agent（报告撰写Agent）
职责：综合所有分析结果，生成结构化投资研究报告
在Pipeline中串行执行，依赖Market Analyst的输出
"""

import logging
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential

from models.report_schema import (
    CollectedData,
    InvestmentReport,
    MarketAnalysis,
    Recommendation,
    SentimentAnalysis,
)

logger = logging.getLogger(__name__)

language_map = {
    "zh": "Chinese",
    "en": "English",
    "ko": "Korean",
    "jp": "Japanese"
}

REPORT_PROMPT = """You are a professional investment research report writer.
Write a comprehensive investment research report in {language} based on the following analysis data.

## Input Data

**Company**: {company_name} ({ticker})
**Sector**: {sector} / {industry}
**Company Description**: {description}

**Financial Highlights**:
- Market Cap: {market_cap}
- P/E Ratio: {pe_ratio}
- P/B Ratio: {pb_ratio}
- ROE: {roe}
- Revenue: {revenue}
- Net Income: {net_income}

**Market Analysis**:
- Trend: {trend}
- Risk Level: {risk_level}
- Recommendation: {recommendation}
- Price Target: {price_target}
- Technical Summary: {tech_summary}
- Analysis: {analysis_summary}

**Sentiment**:
- Overall: {sentiment}
- Score: {sentiment_score}
- Key Topics: {key_topics}
- Summary: {sentiment_summary}

**Risk Factors**:
{risk_factors}

## Requirements

Write the report with these sections. Output in JSON format:
{{
    "title": "投资研究报告标题",
    "executive_summary": "执行摘要（200-300字，涵盖核心观点和投资建议）",
    "company_overview": "公司概况（业务介绍、行业地位、竞争优势）",
    "financial_analysis": "财务分析（核心财务指标分析、盈利能力、成长性）",
    "technical_analysis": "技术分析（趋势分析、关键技术指标、支撑阻力位）",
    "sentiment_overview": "舆情概览（市场情绪、新闻动态、社交媒体热度）",
    "risk_assessment": "风险评估（主要风险因素、严重程度、缓解建议）",
    "investment_recommendation": "投资建议（综合评级、目标价、投资策略）"
}}

Write professionally in {language}. Each section should be 100-200 words.
"""


class ReportWriterAgent:
    """
    报告撰写Agent - 综合分析结果生成结构化投资报告

    输入: CollectedData + SentimentAnalysis + MarketAnalysis
    输出: InvestmentReport

    面试考点:
    - 如何保证报告格式一致性？
      → Pydantic schema强制验证 + 结构化prompt
    - 报告质量如何保证？
      → 多轮生成+自检 + Compliance Agent后续审查
    """

    def __init__(self):
        self.name = "ReportWriterAgent"
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"),
            temperature=0.3,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def execute(
        self,
        collected_data: CollectedData,
        sentiment: SentimentAnalysis,
        market_analysis: MarketAnalysis,
        language: str = "zh",
    ) -> InvestmentReport:
        """执行报告生成"""
        logger.info("[%s] Generating report for %s in %s", self.name, collected_data.ticker, language)

        metrics = collected_data.financial_metrics
        risk_text = "\n".join(
            f"- [{rf.severity.value.upper()}] {rf.category}: {rf.description}"
            for rf in market_analysis.risk_factors
        ) or "No significant risk factors identified."

        tech_summary = "; ".join(
            f"{ti.name}={ti.value} ({ti.signal})"
            for ti in market_analysis.technical_indicators
        ) or "N/A"

        # 获取目标语言
        target_language = language_map.get(language, "Chinese")
        
        prompt = REPORT_PROMPT.format(
            language=target_language,
            company_name=collected_data.company_info.name,
            ticker=collected_data.ticker,
            sector=collected_data.company_info.sector,
            industry=collected_data.company_info.industry,
            description=collected_data.company_info.description[:300],
            market_cap=_fmt(metrics.market_cap),
            pe_ratio=metrics.pe_ratio or "N/A",
            pb_ratio=metrics.pb_ratio or "N/A",
            roe=f"{metrics.roe}%" if metrics.roe else "N/A",
            revenue=_fmt(metrics.revenue),
            net_income=_fmt(metrics.net_income),
            trend=market_analysis.trend_direction,
            risk_level=market_analysis.overall_risk_level.value,
            recommendation=market_analysis.recommendation.value,
            price_target=market_analysis.price_target or "N/A",
            tech_summary=tech_summary,
            analysis_summary=market_analysis.analysis_summary,
            sentiment=sentiment.overall_sentiment.value,
            sentiment_score=sentiment.sentiment_score,
            key_topics=", ".join(sentiment.key_topics),
            sentiment_summary=sentiment.analysis_summary,
            risk_factors=risk_text,
        )

        llm_result = await self._generate_with_llm(prompt)

        report = InvestmentReport(
            title=llm_result.get("title", f"{collected_data.ticker} 投资研究报告"),
            ticker=collected_data.ticker,
            executive_summary=llm_result.get("executive_summary", ""),
            company_overview=llm_result.get("company_overview", ""),
            financial_analysis=llm_result.get("financial_analysis", ""),
            technical_analysis=llm_result.get("technical_analysis", ""),
            sentiment_overview=llm_result.get("sentiment_overview", ""),
            risk_assessment=llm_result.get("risk_assessment", ""),
            investment_recommendation=llm_result.get("investment_recommendation", ""),
            recommendation=market_analysis.recommendation,
            price_target=market_analysis.price_target,
        )

        logger.info("[%s] Report generated: %s", self.name, report.title)
        return report

    async def _generate_with_llm(self, prompt: str) -> dict:
        """使用LLM生成报告内容"""
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
            logger.warning("LLM report generation failed: %s, using fallback", e)
            return {
                "title": "投资研究报告",
                "executive_summary": "报告生成过程中遇到问题，以下为基于可用数据的初步分析。",
                "company_overview": "公司信息加载中...",
                "financial_analysis": "财务数据分析中...",
                "technical_analysis": "技术面分析中...",
                "sentiment_overview": "舆情数据分析中...",
                "risk_assessment": "风险评估中...",
                "investment_recommendation": "请参考市场分析Agent的建议。",
            }


def _fmt(value) -> str:
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
