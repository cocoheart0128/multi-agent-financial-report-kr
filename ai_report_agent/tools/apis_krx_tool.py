"""
SEC EDGAR 文件获取工具
获取上市公司的SEC文件（10-K, 10-Q, 8-K等）
"""

import logging
import asyncio
import os
from typing import Any, Dict, Optional, Union
import httpx
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models.report_schema import CompanyIdentity
from config.read_key import APIS_DATA_KEY

logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

# KRX 상장 종목 정보
KRX_CODE_INFO_BASE = "https://apis.data.go.kr/1160100/service/GetKrxListedInfoService/getItemInfo"
# 재무정보 API
FINANCIAL_INFO_BASE = "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2"
FINANCIAL_ENDPOINTS = {
    "summary": "/getSummFinaStat_V2",   # 요약 재무제표
    "balance_sheet": "/getBs_V2",       # 재무상태표
    "income_statement": "/getIncoStat_V2",  # 손익계산서
}

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

def build_ticker(identity: CompanyIdentity) -> Optional[str]:

    if not identity.stock_code:
        return None

    suffix_map = {
        "KOSPI": "KS",
        "KOSDAQ": "KQ",
        "KONEX": "KN",
    }

    suffix = suffix_map.get(identity.market or "", "")

    return f"{identity.stock_code}.{suffix}" if suffix else identity.stock_code

async def get_krx_comp_identity(itms_nm: str) -> CompanyIdentity:

    params = {
        "serviceKey": APIS_DATA_KEY,
        "resultType": "json",
        "itmsNm": itms_nm,
    }

    parsed = await _call_api_all_pages(
        KRX_CODE_INFO_BASE,
        "",
        params,
        "KRX_ITEM",
    )

    items = parsed["items"]

    if not items:
        return CompanyIdentity(name=itms_nm)

    latest = max(items, key=lambda x: x.get("basDt", ""))

    # 1️⃣ 먼저 identity 생성 (완전하게)
    identity = CompanyIdentity(
        name=latest.get("corpNm") or itms_nm,   # 🔥 fallback 필수
        crno=latest.get("crno"),
        stock_code=(latest.get("srtnCd") or "").replace("A", ""),
        market=latest.get("mrktCtg"),
    )

    # 2️⃣ ticker는 후처리 (enrichment)
    ticker = build_ticker(identity)

    # 3️⃣ 최종 반환
    return identity.model_copy(update={"ticker": ticker})


async def get_financial_all(
    identity: Union[CompanyIdentity, str],
    start_year: str,
    end_year: str,
) -> dict:
    """
    Fetch all financial data for a company using its KRX `crno` for a range of years.

    `identity` may be a `CompanyIdentity` instance or a raw `crno` string.
    `start_year` and `end_year` are inclusive year range (e.g., "2022", "2024")
    """

    # Resolve crno from CompanyIdentity or accept raw string
    if isinstance(identity, CompanyIdentity):
        crno_value = identity.crno
    else:
        crno_value = identity

    if not crno_value:
        logger.warning("get_financial_all: missing crno; returning empty result")
        return {"summary": [], "balance_sheet": [], "income_statement": []}

    # Convert year strings to integers
    try:
        start = int(start_year)
        end = int(end_year)
        if start > end:
            start, end = end, start
    except ValueError:
        logger.error("Invalid year format; returning empty result")
        return {"summary": [], "balance_sheet": [], "income_statement": []}

    base_params = {
        "serviceKey": APIS_DATA_KEY,
        "resultType": "json",
    }

    all_summary = []
    all_bs = []
    all_is = []

    # 각 연도별로 API 호출
    tasks = []
    for year in range(start, end + 1):
        year_str = str(year)

        # Summary 파라미터
        params_sum = base_params.copy()
        params_sum.update({"crno": crno_value, "bizYear": year_str})

        # Balance Sheet 파라미터
        params_bs = base_params.copy()
        params_bs.update({"crno": crno_value, "bizYear": year_str})

        # Income Statement 파라미터
        params_is = base_params.copy()
        params_is.update({"crno": crno_value, "bizYear": year_str})

        tasks.append(
            _call_api_all_pages(
                FINANCIAL_INFO_BASE,
                FINANCIAL_ENDPOINTS["summary"],
                params_sum,
                f"FIN_SUMMARY_{year_str}",
            )
        )
        tasks.append(
            _call_api_all_pages(
                FINANCIAL_INFO_BASE,
                FINANCIAL_ENDPOINTS["balance_sheet"],
                params_bs,
                f"FIN_BS_{year_str}",
            )
        )
        tasks.append(
            _call_api_all_pages(
                FINANCIAL_INFO_BASE,
                FINANCIAL_ENDPOINTS["income_statement"],
                params_is,
                f"FIN_IS_{year_str}",
            )
        )

    # 모든 태스크 동시 실행
    results = await asyncio.gather(*tasks)

    # 결과 병합
    for i in range(0, len(results), 3):
        all_summary.extend(results[i].get("items", []))
        all_bs.extend(results[i + 1].get("items", []))
        all_is.extend(results[i + 2].get("items", []))

    return {
        "summary": all_summary,
        "balance_sheet": all_bs,
        "income_statement": all_is,
    }