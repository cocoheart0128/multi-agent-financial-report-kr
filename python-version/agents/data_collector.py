"""
Data Collector Agent（数据采集Agent）
职责：抓取财报、行情数据、한국 기업 정보, 汇总为结构化数据
在Pipeline中与Sentiment Agent并行执行（Fan-out模式）
"""

import asyncio
import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from models.report_schema import CollectedData, StockQuery
from tools.yahoo_finance_tool import (
    get_financial_metrics,
    get_recent_prices,
    get_company_info,
)
from tools.apis_tool import (
    get_corporate_filings_as_text,
    _mock_filings,
)

logger = logging.getLogger(__name__)


class DataCollectorAgent:
    """
    数据采集Agent - 负责从多个数据源收集金融数据

    数据源:
    1. 한국 공공데이터: 기업 기본 정보, 재무 정보
    2. Yahoo Finance / yfinance: 주식 가격 데이터
    3. 기업 공시정보: 정기보고서, 반기보고서 등

    面试考点:
    - 为什么用Agent而不是简单的函数调用？
      → Agent可以根据数据质量自主决定是否需要补充数据源
    - 如何处理数据源不可用？
      → tenacity重试 + mock数据降级 + 多数据源互补
    """

    def __init__(self):
        self.name = "DataCollectorAgent"
        self.data_sources = ["Korean Stock Market API", "Yahoo Finance", "Corporate Filings"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def execute(self, query: StockQuery) -> CollectedData:
        """
        执行数据采集任务

        采集流程:
        1. 병렬로 회사 정보, 재무 지표, 주가 이력 취득
        2. 비동기로 기업 공시 정보 취득
        3. CollectedData 구조로 통합
        """
        logger.info("[%s] Starting data collection for %s", self.name, query.ticker)

        # 한국 회사 정보 조회 (동기 버전)
        def get_company_info_safe():
            try:
                return get_company_info(query.ticker)
            except Exception as e:
                logger.warning("Failed to get company info: %s, using mock data", e)
                return get_company_info(query.ticker)  # 이미 모의 데이터 반환
        
        # 재무 지표 조회 (동기, 실패 안전)
        def get_metrics_safe():
            try:
                return get_financial_metrics(query.ticker)
            except Exception as e:
                logger.warning("Failed to get financial metrics: %s, using mock data", e)
                return get_financial_metrics(query.ticker)  # 이미 모의 데이터 반환
        
        # 주가 데이터 조회 (동기, 실패 안전)
        def get_prices_safe():
            try:
                return get_recent_prices(query.ticker, query.period)
            except Exception as e:
                logger.warning("Failed to get recent prices: %s, using mock data", e)
                return get_recent_prices(query.ticker, query.period)  # 이미 모의 데이터 반환

        # 병렬로 데이터 조회
        company_info, metrics, prices = await asyncio.gather(
            asyncio.to_thread(get_company_info_safe),
            asyncio.to_thread(get_metrics_safe),
            asyncio.to_thread(get_prices_safe),
        )

        # 공시 정보 조회 (비동기)
        try:
            filings_raw = await get_corporate_filings_as_text(query.ticker)
        except Exception as e:
            logger.warning("Failed to get corporate filings: %s, using mock data", e)
            filings_raw = [
                f"{f['form_type']} ({f['filing_date']}): {f['description']}"
                for f in _mock_filings(query.ticker)
            ]

        logger.debug("[%s] Company info: %s", self.name, company_info)
        logger.debug("[%s] Metrics: %s", self.name, metrics)
        logger.debug("[%s] Prices: %d items", self.name, len(prices) if prices else 0)
        logger.debug("[%s] Filings: %d items", self.name, len(filings_raw))

        result = CollectedData(
            ticker=query.ticker,
            company_info=company_info,
            financial_metrics=metrics,
            recent_prices=prices[-30:] if prices else [],  # 최近30个交易日
            sec_filings=filings_raw if filings_raw else _mock_filings(query.ticker),
            data_sources=self.data_sources,
        )

        logger.info(
            "[%s] Collected data for %s: %d price points, %d filings",
            self.name,
            query.ticker,
            len(result.recent_prices),
            len(result.sec_filings),
        )
        return result
