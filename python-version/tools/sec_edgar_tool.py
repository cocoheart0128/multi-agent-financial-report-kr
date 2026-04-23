"""
SEC EDGAR 文件获取工具
获取上市公司的SEC文件（10-K, 10-Q, 8-K等）
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

SEC_EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
SEC_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
SEC_COMPANY_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions"


async def get_sec_filings(
    ticker: str, filing_types: list[str] | None = None, count: int = 5
) -> list[dict]:
    """
    获取公司最近的SEC文件摘要
    filing_types: 如 ["10-K", "10-Q", "8-K"]
    """
    if filing_types is None:
        filing_types = ["10-K", "10-Q", "8-K"]

    user_agent = os.getenv(
        "SEC_EDGAR_USER_AGENT", "FinReportBot research@example.com"
    )

    try:
        cik = await _get_cik(ticker, user_agent)
        if not cik:
            logger.warning("CIK not found for %s, returning mock data", ticker)
            return _mock_filings(ticker, filing_types)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{EDGAR_SUBMISSIONS_URL}/CIK{cik:0>10}.json",
                headers={"User-Agent": user_agent},
            )
            response.raise_for_status()
            data = response.json()

            filings = []
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            descriptions = recent.get("primaryDocDescription", [])
            accession_numbers = recent.get("accessionNumber", [])

            for i, form in enumerate(forms):
                if form in filing_types and len(filings) < count:
                    filings.append({
                        "form_type": form,
                        "filing_date": dates[i] if i < len(dates) else "",
                        "description": descriptions[i] if i < len(descriptions) else "",
                        "accession_number": accession_numbers[i] if i < len(accession_numbers) else "",
                        "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}",
                    })

            return filings if filings else _mock_filings(ticker, filing_types)

    except Exception as e:
        logger.error("SEC EDGAR fetch failed: %s", e)
        return _mock_filings(ticker, filing_types)


async def _get_cik(ticker: str, user_agent: str) -> str | None:
    """通过ticker获取CIK编号"""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": user_agent},
            )
            response.raise_for_status()
            data = response.json()
            for entry in data.values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    return str(entry["cik_str"])
        except Exception as e:
            logger.error("CIK lookup failed: %s", e)
    return None


def _mock_filings(ticker: str, filing_types: list[str]) -> list[dict]:
    """当API不可用时返回模拟数据"""
    mock_data = []
    for ft in filing_types[:3]:
        mock_data.append({
            "form_type": ft,
            "filing_date": "2025-12-15",
            "description": f"{ticker} {ft} Annual/Quarterly Report (Demo Data)",
            "accession_number": "0001234567-25-000001",
            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?company={ticker}&type={ft}",
        })
    return mock_data
