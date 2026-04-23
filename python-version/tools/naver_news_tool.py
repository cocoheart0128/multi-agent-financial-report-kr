"""
新闻搜索与舆情数据获取工具
支持 NAVER API 搜索金融相关新闻
"""

import logging
import os
from datetime import datetime
from datetime import datetime
from typing import List, Dict
from transformers import pipeline

import httpx

logger = logging.getLogger(__name__)

NAVER_BASE_URL = "https://openapi.naver.com/v1/search/news.json"

# -----------------------------
# 1. 모델 (전역 1회 로드)
# -----------------------------
sentiment_model = pipeline(
    "sentiment-analysis",
    model="snunlp/KR-FinBert"
)


# -----------------------------
# 2. 유틸
# -----------------------------
def clean_html(text: str) -> str:
    return text.replace("<b>", "").replace("</b>", "")


def normalize_score(label: str, score: float) -> float:
    if label.upper() in ["NEGATIVE", "LABEL_0"]:
        return 1 - score
    return score


def parse_date(pub_date: str) -> str:
    try:
        return datetime.strptime(
            pub_date, "%a, %d %b %Y %H:%M:%S %z"
        ).isoformat()
    except Exception:
        return ""

# -----------------------------
# 3. 핵심 함수 (async)
# -----------------------------
async def search_financial_news(
    query: str, max_results: int = 10
) -> List[Dict]:

    api_id = os.getenv("NAVER_CLIENT_ID", "")
    api_key = os.getenv("NAVER_CLIENT_SECRET", "")

    if not api_key:
        logger.warning("NAVER_CLIENT_SECRET not set, returning mock data")
        return _mock_news(query)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                NAVER_BASE_URL,
                headers={
                    "X-Naver-Client-Id": api_id,
                    "X-Naver-Client-Secret": api_key
                },
                params={
                    "query": query,
                    "display": max_results,
                    "sort": "date"
                },
            )

            response.raise_for_status()
            data = response.json()

            results = []

            for item in data.get("items", []):
                title = clean_html(item.get("title", ""))
                content = clean_html(item.get("description", ""))

                # -----------------------------
                # 감성 분석
                # -----------------------------
                text = f"{title}. {content}"[:512]

                try:
                    sentiment = sentiment_model(text)[0]
                    score = normalize_score(
                        sentiment["label"],
                        sentiment["score"]
                    )
                    label = sentiment["label"]
                except Exception as e:
                    logger.warning("Sentiment failed: %s", e)
                    score = 0.5
                    label = "NEUTRAL"

                results.append({
                    "title": title,
                    "url": item.get("originallink") or item.get("link"),
                    "content": content,
                    "published_date": parse_date(item.get("pubDate", "")),
                    "score": round(score, 4),
                    # "sentiment_label": label
                })

            return results

        except Exception as e:
            logger.error("Naver search failed: %s", e)
            return _mock_news(query)


# -----------------------------
# 4. Mock (fallback)
# -----------------------------
def _mock_news(query: str) -> List[Dict]:
    now = datetime.now().isoformat()

    return [
        {
            "title": f"{query} Reports Strong Q4 Earnings",
            "url": "https://example.com/news/1",
            "content": f"{query} exceeded expectations.",
            "published_date": now,
            "score": 0.9,
            "sentiment_label": "POSITIVE"
        }
    ]



# # -----------------------------
# # 5. 실행 테스트 (여기!)
# # -----------------------------
# import asyncio
# from dotenv import load_dotenv
# import os

# load_dotenv()

# if __name__ == "__main__":

#     results = asyncio.run(search_financial_news("삼성전자", max_results=5))
    
#     for r in results:
#         print(r)