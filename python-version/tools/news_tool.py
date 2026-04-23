"""
新闻搜索与舆情数据获取工具
支持 Tavily API 搜索金融相关新闻
"""

import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

TAVILY_BASE_URL = "https://api.tavily.com"


async def search_financial_news(
    query: str, max_results: int = 10
) -> list[dict]:
    """
    使用 Tavily API 搜索金融新闻
    返回新闻列表，每条包含 title, url, content, published_date, score
    """
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set, returning mock data")
        return _mock_news(query)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                f"{TAVILY_BASE_URL}/search",
                json={
                    "api_key": api_key,
                    "query": f"{query} stock market financial news",
                    "search_depth": "advanced",
                    "max_results": max_results,
                    "include_domains": [
                        "reuters.com",
                        "bloomberg.com",
                        "cnbc.com",
                        "wsj.com",
                        "ft.com",
                        "seekingalpha.com",
                        "yahoo.com/finance",
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "published_date": r.get("published_date", ""),
                    "score": r.get("score", 0),
                }
                for r in data.get("results", [])
            ]
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return _mock_news(query)


def _mock_news(query: str) -> list[dict]:
    """当API不可用时返回模拟数据（用于开发和演示）"""
    now = datetime.now().isoformat()
    return [
        {
            "title": f"{query} Reports Strong Q4 Earnings, Beats Expectations",
            "url": "https://example.com/news/1",
            "content": f"{query} announced fourth-quarter results that exceeded analyst expectations, driven by strong demand in core business segments.",
            "published_date": now,
            "score": 0.95,
        },
        {
            "title": f"Analysts Upgrade {query} on Positive Industry Outlook",
            "url": "https://example.com/news/2",
            "content": f"Several Wall Street analysts have upgraded their rating on {query}, citing improving market conditions and strong competitive positioning.",
            "published_date": now,
            "score": 0.88,
        },
        {
            "title": f"{query} Announces New Strategic Partnership",
            "url": "https://example.com/news/3",
            "content": f"{query} has entered into a strategic partnership that could expand its market reach and accelerate revenue growth over the next fiscal year.",
            "published_date": now,
            "score": 0.82,
        },
        {
            "title": f"Market Watch: {query} Faces Regulatory Scrutiny",
            "url": "https://example.com/news/4",
            "content": f"Regulatory agencies are closely monitoring {query}'s recent activities, which could impact operations and stock performance.",
            "published_date": now,
            "score": 0.75,
        },
        {
            "title": f"{query} Sector Shows Mixed Signals Amid Economic Uncertainty",
            "url": "https://example.com/news/5",
            "content": f"The sector where {query} operates shows mixed signals, with some indicators pointing to growth while macroeconomic headwinds persist.",
            "published_date": now,
            "score": 0.70,
        },
    ]
