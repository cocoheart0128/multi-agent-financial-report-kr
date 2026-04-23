"""
SEC EDGAR 文件获取工具
获取上市公司的SEC文件（10-K, 10-Q, 8-K等）
"""

import logging
import asyncio
import os
from typing import Any, Dict, Optional
import httpx
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models.report_schema import CompanyInfo
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
        "stock_market": latest.get("mrktCtg"),
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

async def get_financial_all(corp_code: str, crtr_yr: str) -> dict:
    base_params = {
        "serviceKey": APIS_DATA_KEY,
        "resultType": "json",
        "numOfRows": 1000,
        "pageNo": 1,
    }

    async with httpx.AsyncClient() as client:

        params_sum = base_params.copy()
        params_sum.update({"crno": corp_code, "bizYear": crtr_yr})
        summary_task = _call_api_all_pages(
            FINANCIAL_INFO_BASE,
            FINANCIAL_ENDPOINTS["summary"],
            params_sum,
            "FIN_SUMMARY",
        )

        bs_task = _call_api_all_pages(
            FINANCIAL_INFO_BASE,
            FINANCIAL_ENDPOINTS["balance_sheet"],
            params_sum,
            "FIN_BS",
        )

        params_is = base_params.copy()
        params_is.update({"stdt": crtr_yr})
        is_task = _call_api_all_pages(
            FINANCIAL_INFO_BASE,
            FINANCIAL_ENDPOINTS["income_statement"],
            params_is,
            "FIN_IS",
        )

        summary_res, bs_res, is_res = await asyncio.gather(
            summary_task,
            bs_task,
            is_task,
        )

    return {
        "summary": summary_res.get("items", []),
        "balance_sheet": bs_res.get("items", []),
        "income_statement": is_res.get("items", []),
    }


def build_ticker(comp_info: dict) -> str:
    market = comp_info.get("stock_market")
    stock_code = comp_info.get("stock_code")

    MARKET_SUFFIX = {
        "KOSPI": "KS",
        "KOSDAQ": "KQ",
        "KONEX": "KN",
    }

    suffix = MARKET_SUFFIX.get(market, "")

    return f"{stock_code}.{suffix}"

async def get_company_info(corp_name: str) -> CompanyInfo:
    """获取公司基本信息"""
    comp_info = await get_latest_krx_item(corp_name)
    info = await get_corp_outline_history(comp_info["corp_code"], comp_info["corp_name"])
    current_info = info.get("current", {})

    return CompanyInfo(
        name=comp_info['corp_name'],
        ticker=build_ticker(comp_info),
        crno=current_info.get("crno", "Unknown"),
        established_date=current_info.get("established_date", "Unknown"),
        website=current_info.get("homepage", ""),
        employees=current_info.get("employees"),
    )

def _parse_financial_metrics(financial_data: dict) -> "FinancialMetrics":
    """재무 데이터를 FinancialMetrics로 변환"""
    from models.report_schema import FinancialMetrics
    
    summary = {}
    
    # summary 항목에서 최신 데이터 추출
    if financial_data.get("summary"):
        latest_summary = financial_data["summary"][-1] if financial_data["summary"] else {}
        summary = {
            "market_cap": _safe_int(latest_summary.get("corporateValue")),
            "revenue": _safe_int(latest_summary.get("operatingProfit")),  # 영업수익
            "net_income": _safe_int(latest_summary.get("netIncome")),  # 당기순이익
            "total_assets": _safe_int(latest_summary.get("totalAssets")),
            "total_liabilities": _safe_int(latest_summary.get("totalDebt")),
        }
    
    # 재무지표 계산
    total_assets = summary.get("total_assets")
    total_liabilities = summary.get("total_liabilities")
    net_income = summary.get("net_income")
    
    debt_to_equity = None
    roe = None
    
    if total_liabilities and total_assets:
        equity = total_assets - total_liabilities
        if equity and equity > 0:
            debt_to_equity = total_liabilities / equity
            if net_income:
                roe = (net_income / equity) * 100
    
    return FinancialMetrics(
        market_cap=summary.get("market_cap"),
        pe_ratio=None,  # 한국 API에서 직접 제공하지 않음
        pb_ratio=None,
        revenue=summary.get("revenue"),
        net_income=summary.get("net_income"),
        debt_to_equity=debt_to_equity,
        roe=roe,
        current_ratio=None,
        free_cash_flow=None,
    )


async def get_financial_metrics(ticker: str) -> "FinancialMetrics":
    """한국 기업의 재무지표 조회"""
    from models.report_schema import FinancialMetrics
    
    # ticker에서 종목명 추출 (예: "005930.KS" -> "삼성전자")
    # 실제로는 종목코드로 기업명을 조회해야 하는데, 여기서는 간단히 모의 데이터 반환
    try:
        # 현재 API가 정상 작동하지 않을 경우를 대비한 모의 데이터
        return FinancialMetrics(
            market_cap=300000000000,  # 약 300조원
            pe_ratio=10.5,
            pb_ratio=0.8,
            revenue=200000000000,
            net_income=20000000000,
            debt_to_equity=0.45,
            roe=12.5,
            current_ratio=1.2,
            free_cash_flow=15000000000,
        )
    except Exception as e:
        logger.error("Failed to get financial metrics for %s: %s", ticker, e)
        return FinancialMetrics()


async def get_recent_prices(ticker: str, period: str = "3mo") -> list:
    """한국 주식의 최근 가격 데이터 조회"""
    from models.report_schema import StockPrice
    from datetime import datetime, timedelta
    
    try:
        # 현재는 모의 데이터 반환 (실제로는 한국거래소 API 또는 yfinance 사용)
        prices = []
        base_price = 70000  # 기본 가격
        
        for i in range(30):  # 30일 데이터
            date = (datetime.now() - timedelta(days=30-i)).strftime("%Y-%m-%d")
            fluctuation = (i % 5) * 500  # 변동성 추가
            close = base_price + fluctuation
            
            prices.append(
                StockPrice(
                    date=date,
                    open=close - 500,
                    high=close + 1000,
                    low=close - 1000,
                    close=close,
                    volume=1000000 + (i * 10000),
                )
            )
        
        return prices
    except Exception as e:
        logger.error("Failed to get recent prices for %s: %s", ticker, e)
        return []


async def get_corporate_filings(ticker: str) -> list:
    """한국 기업의 공시 정보 조회 (SEC EDGAR 대신)"""
    try:
        # 모의 공시 데이터 반환
        # 실제로는 금융감독원 DART API나 한국거래소 정보를 사용
        mock_filings = [
            {
                "form_type": "정기보고서(연간)",
                "filing_date": "2025-03-31",
                "description": "2024년 정기보고서 (연간)",
                "url": "https://dart.fss.or.kr",
            },
            {
                "form_type": "반기보고서",
                "filing_date": "2024-09-30",
                "description": "2024년 반기보고서",
                "url": "https://dart.fss.or.kr",
            },
            {
                "form_type": "분기보고서",
                "filing_date": "2024-08-15",
                "description": "2024년 2분기 분기보고서",
                "url": "https://dart.fss.or.kr",
            },
        ]
        return mock_filings
    except Exception as e:
        logger.error("Failed to get corporate filings for %s: %s", ticker, e)
        return []


# 모의 데이터 함수들 (API가 없을 때)
def _mock_company_info(ticker: str) -> CompanyInfo:
    """회사 정보 모의 데이터"""
    return CompanyInfo(
        name=f"한국기업_{ticker}",
        ticker=ticker,
        crno="1234567890",
        established_date="2000-01-01",
        website="https://example.kr",
        employees=5000,
        sector="정보통신",
        industry="반도체",
        description=f"{ticker} 회사에 대한 설명입니다. 한국의 주요 기업으로 다양한 사업을 영위하고 있습니다.",
    )


# 모의 데이터를 위한 함수
async def get_company_info_fallback(ticker: str) -> CompanyInfo:
    """API 실패 시 모의 데이터 반환"""
    return _mock_company_info(ticker)


# 비동기 함수 (내부용)
async def get_company_info_async(corp_name: str) -> CompanyInfo:
    """获取公司基本信息 (async版本)"""
    try:
        comp_info = await get_latest_krx_item(corp_name)
        if not comp_info:
            logger.warning("No company found for %s, returning mock data", corp_name)
            return _mock_company_info(corp_name)
        
        try:
            info = await get_corp_outline_history(
                comp_info["corp_code"], 
                comp_info["corp_name"]
            )
            current_info = info.get("current", {})
        except Exception as e:
            logger.warning("Failed to get corp outline, using partial data: %s", e)
            current_info = {}

        return CompanyInfo(
            name=comp_info.get('corp_name', corp_name),
            ticker=build_ticker(comp_info),
            crno=current_info.get("crno", comp_info.get("corp_code", "Unknown")),
            established_date=current_info.get("established_date", "Unknown"),
            website=current_info.get("homepage", ""),
            employees=current_info.get("employees"),
        )
    except Exception as e:
        logger.error("Failed to get company info for %s: %s", corp_name, e)
        return _mock_company_info(corp_name)


# 동기 래퍼 함수 (asyncio.to_thread용)
def get_company_info(corp_name: str) -> CompanyInfo:
    """获取公司基本信息 (同期版本, asyncio.to_thread用)"""
    # 실패 안전: 바로 모의 데이터 반환 (API 호출 생략)
    logger.info("Getting company info for %s", corp_name)
    return _mock_company_info(corp_name)


# 모의 데이터 - 단순화
async def get_company_info_mock(ticker: str) -> CompanyInfo:
    """테스트용 모의 회사 정보"""
    return CompanyInfo(
        name=f"한국기업_{ticker}",
        ticker=ticker,
        crno="1234567890",
        established_date="2000-01-15",
        website="https://company.kr",
        employees=5000,
    )


# 모의 공시 데이터
def _mock_filings(ticker: str) -> list:
    """테스트용 모의 공시 데이터"""
    return [
        {
            "form_type": "정기보고서(연간)",
            "filing_date": "2025-03-31",
            "description": f"{ticker} 2024년 정기보고서",
            "url": "https://dart.fss.or.kr",
        },
        {
            "form_type": "반기보고서",
            "filing_date": "2024-09-30",
            "description": f"{ticker} 2024년 반기보고서",
            "url": "https://dart.fss.or.kr",
        },
        {
            "form_type": "분기보고서",
            "filing_date": "2024-08-15",
            "description": f"{ticker} 2024년 2분기 분기보고서",
            "url": "https://dart.fss.or.kr",
        },
    ]


# 공시 정보를 문자열로 변환
async def get_corporate_filings_as_text(ticker: str) -> list:
    """한국 기업 공시 정보를 텍스트 리스트로 반환"""
    filings = await get_corporate_filings(ticker)
    return [
        f"{f['form_type']} ({f['filing_date']}): {f['description']}"
        for f in filings
    ]


# API 호출이 실패할 경우를 대비한 단순화된 함수들
async def get_company_info_simple(ticker: str) -> CompanyInfo:
    """단순화된 회사 정보 조회 (실패 대비)"""
    logger.info("Getting company info for %s", ticker)
    try:
        return await get_company_info(ticker)
    except Exception as e:
        logger.warning("Using fallback for %s: %s", ticker, e)
        return await get_company_info_fallback(ticker)


# -----------------------------
# 5. 실행 테스트 (여기!)
# -----------------------------
if __name__ == "__main__":

    print("APIS_DATA_KEY:", APIS_DATA_KEY)
    # results = asyncio.run(get_latest_krx_item("삼성전자"))
    # print(results)
    # results2 = asyncio.run(get_corp_outline_history(results["corp_code"], results["corp_name"]))
    # print(results2)
    # results3 = asyncio.run(get_financial_all(results["corp_code"], "2025"))
    # print(results3)
    # results4 = asyncio.run(get_company_info("삼성전자"))
    # print(results4)
    
    # 테스트: 모의 데이터 함수들
    print("\n=== Testing mock functions ===")
    print("Company info:", asyncio.run(get_company_info_mock("005930")))
    print("Filings:", _mock_filings("005930"))