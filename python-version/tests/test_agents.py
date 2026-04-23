"""
Agent单元测试
测试每个Agent的基本功能和数据模型的序列化
"""

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.report_schema import (
    StockQuery,
    CollectedData,
    CompanyInfo,
    FinancialMetrics,
    SentimentAnalysis,
    SentimentScore,
    MarketAnalysis,
    RiskLevel,
    Recommendation,
    InvestmentReport,
    ComplianceReport,
    FinalReport,
)


class TestModels:
    """测试Pydantic数据模型"""

    def test_stock_query_creation(self):
        query = StockQuery(ticker="AAPL", period="1y", language="zh")
        assert query.ticker == "AAPL"
        assert query.period == "1y"

    def test_stock_query_defaults(self):
        query = StockQuery(ticker="TSLA")
        assert query.period == "1y"
        assert query.language == "zh"

    def test_collected_data_serialization(self):
        data = CollectedData(
            ticker="AAPL",
            company_info=CompanyInfo(name="Apple Inc.", sector="Technology"),
            financial_metrics=FinancialMetrics(market_cap=3e12, pe_ratio=28.5),
            data_sources=["Yahoo Finance"],
        )
        json_str = data.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["ticker"] == "AAPL"
        assert parsed["company_info"]["name"] == "Apple Inc."

    def test_sentiment_score_range(self):
        analysis = SentimentAnalysis(
            ticker="AAPL",
            overall_sentiment=SentimentScore.POSITIVE,
            sentiment_score=0.75,
        )
        assert -1.0 <= analysis.sentiment_score <= 1.0

    def test_risk_levels(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_recommendation_values(self):
        assert Recommendation.STRONG_BUY.value == "strong_buy"
        assert Recommendation.HOLD.value == "hold"

    def test_compliance_report(self):
        report = ComplianceReport(
            is_compliant=True,
            compliance_score=85.0,
        )
        assert report.is_compliant
        assert report.compliance_score == 85.0

    def test_final_report_assembly(self):
        """测试最终报告的组装"""
        final = FinalReport(
            report=InvestmentReport(
                title="Test Report",
                ticker="AAPL",
                executive_summary="Test summary",
                company_overview="Test overview",
                financial_analysis="Test financials",
                technical_analysis="Test technicals",
                sentiment_overview="Test sentiment",
                risk_assessment="Test risks",
                investment_recommendation="Test recommendation",
                recommendation=Recommendation.BUY,
            ),
            compliance=ComplianceReport(
                is_compliant=True,
                compliance_score=90.0,
            ),
            collected_data=CollectedData(
                ticker="AAPL",
                company_info=CompanyInfo(name="Apple Inc."),
                financial_metrics=FinancialMetrics(),
            ),
            sentiment=SentimentAnalysis(
                ticker="AAPL",
                overall_sentiment=SentimentScore.POSITIVE,
                sentiment_score=0.6,
            ),
            market_analysis=MarketAnalysis(
                ticker="AAPL",
                trend_direction="uptrend",
                overall_risk_level=RiskLevel.LOW,
                recommendation=Recommendation.BUY,
            ),
        )
        assert final.report.ticker == "AAPL"
        assert final.compliance.is_compliant


class TestDataCollector:
    """测试数据采集Agent（使用mock数据）"""

    def test_yahoo_finance_import(self):
        from tools.yahoo_finance_tool import get_company_info
        assert callable(get_company_info)

    def test_news_tool_import(self):
        from tools.news_tool import search_financial_news
        assert callable(search_financial_news)

    def test_sec_tool_import(self):
        from tools.sec_edgar_tool import get_sec_filings
        assert callable(get_sec_filings)


class TestOrchestrator:
    """测试编排器的基本结构"""

    def test_orchestrator_creation(self):
        from orchestrator import ReportOrchestrator
        orch = ReportOrchestrator()
        assert orch.data_collector is not None
        assert orch.sentiment_agent is not None
        assert orch.market_analyst is not None
        assert orch.report_writer is not None
        assert orch.compliance_agent is not None

    def test_all_agents_have_execute(self):
        from agents import (
            DataCollectorAgent,
            SentimentAgent,
            MarketAnalystAgent,
            ReportWriterAgent,
            ComplianceAgent,
        )
        for agent_cls in [
            DataCollectorAgent,
            SentimentAgent,
            MarketAnalystAgent,
            ReportWriterAgent,
            ComplianceAgent,
        ]:
            agent = agent_cls()
            assert hasattr(agent, "execute")
            assert asyncio.iscoroutinefunction(agent.execute)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
