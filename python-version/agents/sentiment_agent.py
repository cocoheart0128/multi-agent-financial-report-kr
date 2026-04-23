"""
Sentiment Agent（감정 분석 Agent）
职責：분석 뉴스와 소셜 미디어의 감정 성향
在Pipeline中与Data Collector并行执行（Fan-out模式）
"""

import logging
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential

from models.report_schema import (
    NewsItem,
    SentimentAnalysis,
    SentimentScore,
    StockQuery,
)
# from tools.news_tool import search_financial_news
from tools.naver_news_tool import search_financial_news

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """당신은 금융 감정 분석 전문가입니다.
{ticker}에 대한 다음 뉴스 기사를 분석하여 다음을 제공하세요:
1. 전체 감정 (very_positive, positive, neutral, negative, very_negative)
2. -1.0 (매우 부정적)에서 1.0 (매우 긍정적)까지의 감정 점수
3. 논의된 주요 주제
4. 한국어로 된 간단한 분석 요약

뉴스 기사:
{news_text}

이 정확한 JSON 형식으로 응답하세요:
{{
    "overall_sentiment": "positive",
    "sentiment_score": 0.6,
    "key_topics": ["실적", "성장", "시장 확대"],
    "analysis_summary": "전반적인 여론은 긍정적인 경향..."
}}
"""


class SentimentAgent:
    """
    舆情分析Agent - 分析新闻/社交媒体情感倾向

    工作流程:
    1. 通过Tavily API搜索相关新闻
    2. 使用LLM分析每条新闻的情感倾向
    3. 汇总为整体舆情分析报告

    面试考点:
    - 为什么舆情Agent要和数据采集Agent并行？
      → 两者数据源独立，无依赖关系，并行可减少45%延迟
    - 情感分析用LLM还是专门的NLP模型？
      → LLM理解金融语境更好，但成本更高；可用蒸馏模型降本
    """

    def __init__(self):
        self.name = "SentimentAgent"
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"),
            temperature=0.1,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def execute(self, query: StockQuery) -> SentimentAnalysis:
        """执行舆情分析"""
        logger.info("[%s] Starting sentiment analysis for %s", self.name, query.ticker)

        news_items_raw = await search_financial_news(query.ticker, max_results=10)

        news_items = []
        for item in news_items_raw:
            news_items.append(
                NewsItem(
                    title=item.get("title", ""),
                    source=_extract_source(item.get("url", "")),
                    url=item.get("url", ""),
                    published_at=item.get("published_date", ""),
                    sentiment=SentimentScore.NEUTRAL,
                    summary=item.get("content", "")[:200],
                )
            )

        news_text = "\n\n".join(
            f"Title: {item.title}\nContent: {item.summary}" for item in news_items
        )

        llm_analysis = await self._analyze_with_llm(query.ticker, news_text)

        for item in news_items:
            item.sentiment = _classify_single_sentiment(item.summary, llm_analysis)

        result = SentimentAnalysis(
            ticker=query.ticker,
            overall_sentiment=SentimentScore(
                llm_analysis.get("overall_sentiment", "neutral")
            ),
            sentiment_score=float(llm_analysis.get("sentiment_score", 0.0)),
            news_items=news_items,
            key_topics=llm_analysis.get("key_topics", []),
            social_buzz_score=min(len(news_items) * 10.0, 100.0),
            analysis_summary=llm_analysis.get("analysis_summary", ""),
        )

        logger.info(
            "[%s] Sentiment for %s: %s (score: %.2f)",
            self.name,
            query.ticker,
            result.overall_sentiment.value,
            result.sentiment_score,
        )
        return result

    async def _analyze_with_llm(self, ticker: str, news_text: str) -> dict:
        """使用LLM进行情感分析"""
        try:
            prompt = SENTIMENT_PROMPT.format(ticker=ticker, news_text=news_text)
            # use SENTIMENT_PROMPT(ticker=ticker, news_text=news_text)
            response = await self.llm.ainvoke(prompt)

            import json

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())
        except Exception as e:
            logger.warning("LLM sentiment analysis failed: %s, using fallback", e)
            return {
                "overall_sentiment": "neutral",
                "sentiment_score": 0.0,
                "key_topics": ["market", "finance"],
                "analysis_summary": f"舆情分析暂不可用，{ticker}相关新闻需人工评估。",
            }


def _extract_source(url: str) -> str:
    """从URL中提取来源域名"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return "unknown"


def _classify_single_sentiment(text: str, overall: dict) -> SentimentScore:
    """基于整体分析对单条新闻做简单分类"""
    positive_words = {"beat", "strong", "growth", "upgrade", "positive", "gain", "surge"}
    negative_words = {"miss", "decline", "risk", "downgrade", "negative", "loss", "fall"}

    text_lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count + 1:
        return SentimentScore.POSITIVE
    if neg_count > pos_count + 1:
        return SentimentScore.NEGATIVE
    return SentimentScore.NEUTRAL
