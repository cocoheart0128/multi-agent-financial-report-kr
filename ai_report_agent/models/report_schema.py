"""
结构化报告数据模型 - 使用Pydantic v2强制JSON Schema
所有Agent的输入输出都通过这些模型来约束，确保数据一致性
"""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List


class CompanyIdentity(BaseModel):
    name: str
    # KRX 계열
    crno: Optional[str] = None        # 사업자등록번호
    # 시장 계열
    stock_code: Optional[str] = None  # 005930
    market: Optional[str] = None      # KOSPI/KOSDAQ
    # Yahoo/Global
    ticker: Optional[str] = None      # 005930.KS

class FinancialSummary(BaseModel):
    base_date: Optional[str] = Field(None, alias="basDt")
    biz_year: Optional[str] = Field(None, alias="bizYear")
    corp_code: Optional[str] = Field(None, alias="crno")
    currency: Optional[str] = Field(None, alias="curCd")

    revenue: Optional[int] = Field(None, alias="enpSaleAmt")
    operating_profit: Optional[int] = Field(None, alias="enpBzopPft")
    net_income: Optional[int] = Field(None, alias="enpCrtmNpf")
    pretax_income: Optional[int] = Field(None, alias="iclsPalClcAmt")

    total_assets: Optional[int] = Field(None, alias="enpTastAmt")
    total_liabilities: Optional[int] = Field(None, alias="enpTdbtAmt")
    total_equity: Optional[int] = Field(None, alias="enpTcptAmt")
    capital: Optional[int] = Field(None, alias="enpCptlAmt")

    debt_ratio: Optional[float] = Field(None, alias="fnclDebtRto")

class FinancialAccount(BaseModel):
    account_id: Optional[str] = Field(None, alias="acitId")
    account_name: Optional[str] = Field(None, alias="acitNm")

    base_date: Optional[str] = Field(None, alias="basDt")
    biz_year: Optional[str] = Field(None, alias="bizYear")
    corp_code: Optional[str] = Field(None, alias="crno")

    current: Optional[int] = Field(None, alias="crtmAcitAmt")
    previous: Optional[int] = Field(None, alias="pvtrAcitAmt")
    previous2: Optional[int] = Field(None, alias="bpvtrAcitAmt")

    quarter: Optional[int] = Field(None, alias="thqrAcitAmt")
    last_quarter: Optional[int] = Field(None, alias="lsqtAcitAmt")

class FinancialDataset(BaseModel):
    summary: FinancialSummary
    balance_sheet: List[FinancialAccount]
    income_statement: List[FinancialAccount]

class CompanyInfo(BaseModel):
    name: str
    ticker: str
    crno: str

    established_date: Optional[str] = None
    website: Optional[str] = None
    employees: Optional[int] = None


class StockPrice(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketSnapshot(BaseModel):
    ticker: str
    current_price: Optional[float]
    market_cap: Optional[float]
    pe_ratio: Optional[float]

    history: List[StockPrice]