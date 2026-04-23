import asyncio
import logging
from datetime import datetime


from tools.apis_krx_tool import get_krx_comp_identity, get_financial_all
from tools.naver_news_tool import search_financial_news
from tools.yahoo_finance_tool import get_recent_prices, get_stock_current_price

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    company = "삼성전자"

    # 1. KRX → identity 생성
    identity = await get_krx_comp_identity(company)

    print("\n=== COMPANY IDENTITY ===")
    print(identity.model_dump())

    if not identity.crno:
        logger.warning(f"Company '{company}' has no CRNO; skipping financial data fetch")
    else:
        logger.info(f"✓ Company CRNO: {identity.crno}")

    # 2. NEWS
    news = await search_financial_news(identity)

    print("\n=== NEWS RESULTS ===")
    for n in news[:5]:
        print(n)

    # 3. FINANCIAL DATA - 최근 3년 데이터 수집
    if identity.crno:
        current_year = datetime.now().year
        start_year = str(current_year - 3)  # 3년 전부터
        end_year = str(current_year - 1)    # 작년까지
        logger.info(f"Fetching financial data for {identity.name} (CRNO: {identity.crno}) - Year Range: {start_year}~{end_year}")
        
        # CompanyIdentity 객체 또는 crno 문자열 모두 가능
        financial_data = await get_financial_all(identity, start_year, end_year)

        print("\n=== FINANCIAL RESULTS ===")
        for key, items in financial_data.items():
            print(f"\n{key.upper()}: {len(items)} items")
            if items and len(items) > 0:
                print(f"  Sample: {items[0]}")
    else:
        logger.warning("Skipping financial data fetch - no CRNO")

    # 4. STOCK DATA - Yahoo Finance
    if identity.ticker:
        logger.info(f"Fetching stock data for {identity.name} (Ticker: {identity.ticker})")
        
        current_price = get_stock_current_price(identity)
        recent_prices = get_recent_prices(identity, period="6mo")

        print("\n=== STOCK PRICE DATA ===")
        print(f"Current Price Info:")
        for key, value in current_price.items():
            print(f"  {key}: {value}")
        
        print(f"\nRecent Prices: {len(recent_prices)} data points")
        if recent_prices:
            print(f"  Latest: {recent_prices[-1]}")
            print(f"  Oldest: {recent_prices[0]}")
    else:
        logger.warning("Skipping stock data fetch - no ticker")

if __name__ == "__main__":
    asyncio.run(main())