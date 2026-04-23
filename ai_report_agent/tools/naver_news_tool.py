"""
新闻搜索与舆情数据获取工具
支持 NAVER API 搜索金融相关新闻
"""

import logging
import os
import re
from datetime import datetime
from datetime import datetime
from typing import List, Dict
from transformers import pipeline
from models.report_schema import CompanyIdentity
import httpx
from config.read_key import NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

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

def build_news_query(identity: CompanyIdentity) -> str:

    if identity.name:
        name = re.sub(r"\([^)]*\)", "", identity.name)

    return name.strip() if name else None
# -----------------------------
# 3. 핵심 함수 (async)
# -----------------------------
async def search_financial_news(
    identity: CompanyIdentity,
    max_results: int = 10
) -> List[Dict]:

    query = build_news_query(identity)

    logger.info(f"[NEWS QUERY] {query}")

    if not NAVER_CLIENT_SECRET or not NAVER_CLIENT_ID:
        print("NAVER API 키가 설정되지 않았습니다. 빈 결과를 반환합니다.")
        return ' {"items": []}'  # API 키가 없으면 빈 결과 반환

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            NAVER_BASE_URL,
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
            },
            params={
                "query": query,
                "display": max_results,
                "sort": "date"
            },
        )
        print('--------- query:', query)

        data = response.json()

        results = []
        for item in data.get("items", []):
            title = clean_html(item.get("title", ""))
            content = clean_html(item.get("description", ""))

            text = f"{title}. {content}"[:512]

            try:
                sentiment = sentiment_model(text)[0]
                score = normalize_score(sentiment["label"], sentiment["score"])
            except:
                score = 0.5

            results.append({
                "title": title,
                "url": item.get("link"),
                "score": score,
            })

        return results