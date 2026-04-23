import streamlit as st
import asyncio
import logging
import pandas as pd

from tools.apis_krx_tool import get_krx_comp_identity, get_financial_all
from tools.naver_news_tool import search_financial_news
from tools.yahoo_finance_tool import get_recent_prices, get_stock_current_price

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="KR Financial AI Agent", layout="wide")


def run_async(coro):
    return asyncio.run(coro)


st.title("📊 Korean Stock AI Research Agent")
st.markdown("KRX + NAVER News Sentiment 분석")


# -----------------------------
# INPUT
# -----------------------------
company = st.text_input("회사명 입력", value="삼성전자")

col1, col2 = st.columns(2)

with col1:
    start_year = st.text_input("시작 연도", value="2022")

with col2:
    end_year = st.text_input("종료 연도", value="2024")

news_count = st.slider(
    "뉴스 개수",
    min_value=5,
    max_value=50,
    value=10,
    step=5
)

# -----------------------------
# RUN
# -----------------------------
if st.button("Run Analysis"):

    with st.spinner("KRX Identity fetching..."):
        identity = run_async(get_krx_comp_identity(company))

    st.subheader("🏢 Company Identity")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("회사명", identity.name)
    with col2:
        st.metric("Ticker", identity.ticker)
    with col3:
        st.metric("시장", identity.market)
    with col4:
        st.metric("CRNO", identity.crno)

    # Yahoo Finance 데이터
    if identity.ticker:
        with st.spinner("Yahoo Finance data fetching..."):
            current_price = get_stock_current_price(identity)
            recent_prices = get_recent_prices(identity, period="6mo")

        st.subheader("📈 Stock Price Information")
        
        # 현재 주가 정보
        if current_price:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Current Price", f"{current_price.get('current_price', 'N/A')}")
            with col2:
                st.metric("Day High", f"{current_price.get('day_high', 'N/A')}")
            with col3:
                st.metric("Day Low", f"{current_price.get('day_low', 'N/A')}")
            with col4:
                st.metric("52W High", f"{current_price.get('fifty_two_week_high', 'N/A')}")
        
        # 최근 주가 차트
        if recent_prices:
            prices_df = pd.DataFrame([{
                "Date": p.date,
                "Close": p.close,
                "Volume": p.volume
            } for p in recent_prices])
            
            st.write("#### 📊 Stock Price Trend (6 Months)")
            st.line_chart(prices_df.set_index("Date")[["Close"]])
            
            with st.expander("📋 Historical Price Data"):
                st.dataframe(prices_df, use_container_width=True)

    with st.spinner("Financial data fetching..."):
        financial_data = run_async(get_financial_all(identity, start_year, end_year))

    st.subheader("💰 Financial Information")
    if financial_data and any(financial_data.values()):
        
        # Summary 차트 - fnclDcdNm별
        if financial_data.get("summary"):
            st.write("#### 📊 Summary by Financial Code")
            summary_df = pd.DataFrame(financial_data["summary"])
            
            with st.expander("📋 Summary Data Details"):
                st.dataframe(summary_df, use_container_width=True)
        
        # Balance Sheet 차트 - fnclDcdNm, acitNm별
        if financial_data.get("balance_sheet"):
            st.write("#### 📊 Balance Sheet by Account")
            bs_df = pd.DataFrame(financial_data["balance_sheet"])
            
            # fnclDcdNm과 acitNm 조합으로 그룹화
            if "fnclDcdNm" in bs_df.columns and "acitNm" in bs_df.columns:
                bs_grouped = bs_df.groupby(["fnclDcdNm", "acitNm"]).size().reset_index(name="Count")
            
            with st.expander("📋 Balance Sheet Data Details"):
                st.dataframe(bs_df, use_container_width=True)
        
        # Income Statement 차트 - fnclDcdNm별
        if financial_data.get("income_statement"):
            st.write("#### 📊 Income Statement by Financial Code")
            is_df = pd.DataFrame(financial_data["income_statement"])
            
            # fnclDcdNm 별로 그룹화
            # if "fnclDcdNm" in is_df.columns:
            #     is_grouped = is_df.groupby("fnclDcdNm").size().reset_index(name="Count")
            #     st.bar_chart(is_grouped.set_index("fnclDcdNm"))
            
            with st.expander("📋 Income Statement Data Details"):
                st.dataframe(is_df, use_container_width=True)
    else:
        st.warning("No financial data available")

    with st.spinner("News fetching + sentiment analysis..."):
        news = run_async(
            search_financial_news(
                identity,
                max_results=news_count   # 🔥 여기 핵심
            )
        )

    st.subheader("📰 News Sentiment Results")

    if news:

        st.dataframe(news, use_container_width=True)

        # -----------------------------
        # sentiment chart
        # -----------------------------
        st.subheader("📈 Sentiment Score")

        scores = [n["score"] for n in news]
        st.bar_chart(scores)

        # -----------------------------
        # detail view
        # -----------------------------
        st.subheader("🔍 Detailed News")

        for i, n in enumerate(news):
            with st.expander(f"{i+1}. {n['title']}"):
                st.write("URL:", n.get("url"))
                st.write("Score:", n.get("score"))
                st.write(n.get("content", ""))

    else:
        st.warning("No news found")