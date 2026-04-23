"""
SEC EDGAR 文件获取工具
获取上市公司的SEC文件（10-K, 10-Q, 8-K等）
"""

import logging
import asyncio
import os
from typing import Any, Dict, Optional
import httpx
from dotenv import load_dotenv


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# KRX 상장 종목 정보
KRX_CODE_INFO_BASE = "https://apis.data.go.kr/1160100/service/GetKrxListedInfoService/getItemInfo"
# 기업 기본 정보 (계열/종속 포함)
CORP_BASIC_INFO_BASE = "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2"
# 세부 API Endpoint
CORP_INFO_ENDPOINTS = {
    "corp_outline": "/getCorpOutline_V2", ##기업개요조회
    "subsidiaries": "/getConsSubsComp_V2",##연결대상종속기업조회
    "affiliates": "/getAffiliate_V2",##계열회사조회
}

# 재무정보 API
FINANCIAL_INFO_BASE = "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2"
FINANCIAL_ENDPOINTS = {
    "summary": "/getSummFinaStat_V2",   # 요약 재무제표
    "balance_sheet": "/getBs_V2",       # 재무상태표
    "income_statement": "/getIncoStat_V2",  # 손익계산서
}

load_dotenv()
APIS_DATA_KEY = os.getenv("APIS_DATA_KEY", "")

# ---------------------------
# 공통 API 호출
# ---------------------------
async def _fetch_api(
    base_url: str,
    endpoint: str,
    params: dict,
) -> Optional[dict]:
    async with httpx.AsyncClient() as client:
        try:
            url = f"{base_url}{endpoint}"
            res = await client.get(url, params=params)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error("API error [%s]: %s", endpoint, e)
            return None
    
def _parse_response(data: Optional[dict], api_name: str = "") -> dict:
    """
    공공데이터 표준 응답 파싱

    return:
    {
        "header": {...},
        "meta": {...},
        "items": [...]
    }
    """

    if not data:
        logger.warning("[%s] Empty response", api_name)
        return {"header": {}, "meta": {}, "items": []}

    try:
        response = data.get("response", {})

        # ---------------------------
        # 1️⃣ HEADER 파싱
        # ---------------------------
        header = response.get("header", {})
        result_code = header.get("resultCode")
        result_msg = header.get("resultMsg")

        if result_code != "00":
            logger.error(
                "[%s] API Error - code: %s, msg: %s",
                api_name,
                result_code,
                result_msg,
            )
            return {"header": header, "meta": {}, "items": []}

        # ---------------------------
        # 2️⃣ BODY 파싱
        # ---------------------------
        body = response.get("body", {})

        meta = {
            "num_of_rows": body.get("numOfRows"),
            "page_no": body.get("pageNo"),
            "total_count": body.get("totalCount"),
        }

        # ---------------------------
        # 3️⃣ ITEMS 파싱
        # ---------------------------
        items = body.get("items", {}).get("item", [])

        # 🔥 단건 대응 (item이 dict인 경우)
        if isinstance(items, dict):
            items = [items]

        # ---------------------------
        # 4️⃣ 로깅
        # ---------------------------
        logger.info(
            "[%s] SUCCESS - total: %s, returned: %s",
            api_name,
            meta["total_count"],
            len(items),
        )

        return {
            "header": header,
            "meta": meta,
            "items": items,
        }

    except Exception as e:
        logger.exception("[%s] Parsing failed: %s", api_name, e)
        return {"header": {}, "meta": {}, "items": []}

async def _call_api(
    base_url: str,
    endpoint: str,
    params: dict,
    api_name: str,
) -> dict:
    raw_data = await _fetch_api(base_url, endpoint, params)

    return _parse_response(raw_data, api_name)


async def _call_api_all_pages(
    base_url: str,
    endpoint: str,
    params: dict,
    api_name: str,
    page_size: int = 1000,
) -> dict:

    all_items = []
    page_no = 1

    final_header = {}
    final_meta = {}

    while True:
        req_params = params.copy()
        req_params.update({
            "pageNo": page_no,
            "numOfRows": page_size,
        })

        parsed = await _call_api(
            base_url,
            endpoint,
            req_params,
            api_name,
        )

        items = parsed.get("items", [])
        meta = parsed.get("meta", {})
        header = parsed.get("header", {})

        # 첫 페이지 기준으로 header/meta 저장
        if page_no == 1:
            final_header = header
            final_meta = meta

        if not items:
            break

        all_items.extend(items)

        total_count = int(meta.get("total_count") or 0)

        if total_count:
            if page_no * page_size >= total_count:
                break
        else:
            if len(items) < page_size:
                break

        page_no += 1

    return {
        "header": final_header,
        "meta": final_meta,
        "items": all_items,
    }


async def get_latest_krx_item(itms_nm: str) -> dict:
    params = {
        "serviceKey": APIS_DATA_KEY,
        "resultType": "json",
        "numOfRows": 50,
        "pageNo": 1,
        "itmsNm": itms_nm,
    }

    # parsed = await _call_api(KRX_CODE_INFO_BASE,"",params,"KRX_ITEM",)
    parsed = await _call_api_all_pages(KRX_CODE_INFO_BASE,"",params,"KRX_ITEM",)

    items = parsed["items"]
    if not items:
        return {}

    latest = max(items, key=lambda x: x.get("basDt", ""))

    return {
        "base_dt": latest.get("basDt"),
        "corp_name": latest.get("corpNm"),
        "stock_name": latest.get("itmsNm"),
        "stock_code": latest.get("srtnCd", "").replace("A", ""),
        "corp_code": latest.get("crno"),
    }

def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _build_corp_outline_history(items: list[dict]) -> dict:
    if not items:
        return {"current": {}, "history": []}

    # 1️⃣ 날짜 기준 정렬 (오름차순)
    sorted_items = sorted(items, key=lambda x: x.get("fstOpegDt", ""))

    history = []

    for row in sorted_items:
        history.append({"valid_from": row.get("fstOpegDt"),"valid_to": row.get("lastOpegDt"),
            "data": {
                    # 🧠 경영
                    "ceo": row.get("enpRprFnm"),
                    # 📊 조직
                    "employees": _safe_int(row.get("enpEmpeCnt")),
                    "avg_salary": _safe_int(row.get("enpPn1AvgSlryAmt")),
                    # ⚠️ 리스크
                    "audit": {
                        "auditor": row.get("actnAudpnNm"),
                        "opinion": row.get("audtRptOpnnCtt"),},
                    # 🏭 사업
                    "industry": row.get("sicNm"),
                    "main_business": row.get("enpMainBizNm"),
                    # 🏦 시장
                    "market_type": row.get("corpRegMrktDcdNm"),
                    "listed_date": row.get("enpXchgLstgDt"),} ## 기업의 거래소 상장 일자
                    })

    # 2️⃣ 최신 데이터 (lastOpegDt 기준)
    latest = max(sorted_items, key=lambda x: x.get("lastOpegDt", ""))

    current = {
        "ceo": latest.get("enpRprFnm"),
        "established_date": latest.get("enpEstbDt"),
        "crno": latest.get("crno"),
        "bzno": latest.get("bzno"),
        "employees": _safe_int(latest.get("enpEmpeCnt")),
        "avg_salary": _safe_int(latest.get("enpPn1AvgSlryAmt")),
        "auditor": latest.get("actnAudpnNm"),
        "audit_opinion": latest.get("audtRptOpnnCtt"),
        "address": latest.get("enpBsadr"),
        "homepage": latest.get("enpHmpgUrl"),
        "updated_at": latest.get("lastOpegDt"),
    }

    return {
        "current": current,
        "history": history
    }

async def get_corp_outline_history(corp_code: str, corp_name: str) -> dict:
    params = {
        "serviceKey": APIS_DATA_KEY,
        "resultType": "json",
        "crno": corp_code,
        "corpNm":corp_name,
        "numOfRows": 10000,
        "pageNo": 1,
    }

    async with httpx.AsyncClient() as client:
        parsed = await _call_api_all_pages(
            CORP_BASIC_INFO_BASE,
            CORP_INFO_ENDPOINTS["corp_outline"],
            params,
            "CORP_OUTLINE",
        )

        items = parsed["items"]

    return _build_corp_outline_history(items)

# -----------------------------
# 5. 실행 테스트 (여기!)
# -----------------------------
if __name__ == "__main__":

    print("APIS_DATA_KEY:", APIS_DATA_KEY)
    results = asyncio.run(get_latest_krx_item("삼성전자"))
    print(results)
    results2 = asyncio.run(get_corp_outline_history(results["corp_code"], results["corp_name"]))
    print(results2)