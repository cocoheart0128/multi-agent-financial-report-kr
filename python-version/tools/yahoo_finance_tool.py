"""
Yahoo Finance 数据获取工具
封装 yfinance 库，提供股票行情、财务数据、公司信息的统一接口
"""

import logging
from datetime import datetime, timedelta

import yfinance as yf

from models.report_schema import CompanyInfo, FinancialMetrics, StockPrice

logger = logging.getLogger(__name__)


def get_company_info(ticker: str) -> CompanyInfo:
    """获取公司基本信息 - 한국 기업용 (동기 버전)"""
    # 모의 데이터만 반환 (실제 API는 apis_tool에서 처리)
    return CompanyInfo(
        name=f"Company {ticker}",
        ticker=ticker,
        crno="Unknown",
        established_date="Unknown",
        website="",
        employees=None,
        sector="Unknown",
        industry="Unknown",
        description="",
    )


def get_financial_metrics(ticker: str) -> FinancialMetrics:
    """获取关键财务指标"""
    stock = yf.Ticker(ticker)
    info = stock.info

    return FinancialMetrics(
        market_cap=info.get("marketCap"),
        pe_ratio=info.get("trailingPE"),
        pb_ratio=info.get("priceToBook"),
        dividend_yield=_safe_percent(info.get("dividendYield")),
        revenue=info.get("totalRevenue"),
        net_income=info.get("netIncomeToCommon"),
        debt_to_equity=info.get("debtToEquity"),
        roe=_safe_percent(info.get("returnOnEquity")),
        current_ratio=info.get("currentRatio"),
        free_cash_flow=info.get("freeCashflow"),
    )


def get_recent_prices(ticker: str, period: str = "3mo") -> list[StockPrice]:
    """获取近期股价数据"""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)

    prices = []
    for date, row in hist.iterrows():
        prices.append(
            StockPrice(
                date=date.strftime("%Y-%m-%d"),
                open=round(row["Open"], 2),
                high=round(row["High"], 2),
                low=round(row["Low"], 2),
                close=round(row["Close"], 2),
                volume=int(row["Volume"]),
            )
        )
    return prices


def get_stock_current_price(ticker: str) -> dict:
    """获取当前股价和涨跌幅"""
    stock = yf.Ticker(ticker)
    info = stock.info
    return {
        "current_price": info.get("currentPrice", info.get("regularMarketPrice")),
        "previous_close": info.get("previousClose"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "fifty_day_average": info.get("fiftyDayAverage"),
        "two_hundred_day_average": info.get("twoHundredDayAverage"),
    }


def _safe_percent(value) -> float | None:
    """安全地将小数转为百分比"""
    if value is None:
        return None
    try:
        return round(float(value) * 100, 2)
    except (TypeError, ValueError):
        return None
