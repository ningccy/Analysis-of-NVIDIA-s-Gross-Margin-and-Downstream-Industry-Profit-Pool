import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

TICKER_NAME_MAP = {
    "NVDA": "NVIDIA",
    "3017.TW": "奇鋐科技",
    "2382.TW": "廣達電腦",
    "2357.TW": "華碩電腦",
}

def get_engine():
    db = st.secrets["tidb"]
    return create_engine(
        f"mysql+pymysql://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT']}/{db['DB_NAME']}",
        connect_args={"ssl": {"ssl_verify_cert": False}}
    )

@st.cache_data(show_spinner=False)
def load_and_clean_data():
    engine = get_engine()
    df_raw = pd.read_sql("""
        SELECT ticker, fiscal_quarter, revenue, cogs, operating_income 
        FROM financial_reports
        WHERE ticker IN ('NVDA', '3017.TW', '2382.TW', '2357.TW')
    """, engine)

    if df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()
    df["display_quarter"] = df["fiscal_quarter"]
    df["company_name"] = df["ticker"].map(TICKER_NAME_MAP).fillna(df["ticker"])

    nvda_mask = df["ticker"] == "NVDA"
    if not df[nvda_mask].empty:
        df.loc[nvda_mask, "display_quarter"] = (
            pd.PeriodIndex(df.loc[nvda_mask, "fiscal_quarter"], freq="Q") - 1
        ).astype(str)

    df["operating_income"] = df["operating_income"].fillna(df["revenue"] - df["cogs"])
    safe_revenue = df["revenue"].replace(0, pd.NA)
    df["gross_margin_pct"] = ((df["revenue"] - df["cogs"]) / safe_revenue * 100).round(2)
    df["operating_margin_pct"] = (df["operating_income"] / safe_revenue * 100).round(2)

    df = df.sort_values(["ticker", "fiscal_quarter"])
    df["revenue_qoq"] = df.groupby("ticker")["revenue"].pct_change(1).mul(100).round(2)
    df["revenue_yoy"] = df.groupby("ticker")["revenue"].pct_change(4).mul(100).round(2)

    return df
