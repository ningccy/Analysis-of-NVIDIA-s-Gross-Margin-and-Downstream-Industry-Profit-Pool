import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os 
import plotly.express as px
from dotenv import load_dotenv

st.set_page_config(page_title = "AI 供應鏈利潤池看板", layout = "wide")
load_dotenv()

@st.cache_resource
def get_db_engine():
    db_config = st.secrets["tidb"]
    
    HOST = db_config["HOST"]
    PORT = db_config["PORT"]
    USER = db_config["USER"]
    PASSWORD = db_config["PASSWORD"]
    DB_NAME = db_config["DB_NAME"]

    local_connect_args = {"ssl": {"ssl_verify_cert": False}}

    return create_engine(
            f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}",
            connect_args=local_connect_args,
        )
engine = get_db_engine()

st.title("📊 半導體與 AI 伺服器產業利潤池分析")
st.markdown("本看板追蹤從上游晶片（NVIDIA）到下游組裝與品牌廠的利潤分配與定價權轉嫁。")
st.divider()

st.sidebar.header("💠 控制面板")

if st.sidebar.button("🔄 立即從 API 同步最新財報資料"):
    with st.spinner("正在從 FinMind 與 yfinance 抓取並同步資料至 TiDB..."):
        try:
            nvda = yf.Ticker("NVDA")
            df_nvda_raw = nvda.quarterly_financials
            if not df_nvda_raw.empty:
                df_nvda = df_nvda_raw.T
                df_nvda.index = pd.to_datetime(df_nvda.index)
                df_nvda['fiscal_quarter'] = df_nvda.index.to_period('Q').astype(str)
                df_nvda_standard = df_nvda.rename(columns={'Total Revenue': 'revenue', 'Cost Of Revenue': 'cogs', 'Operating Income': 'operating_income'})
                df_nvda_standard['ticker'] = 'NVDA'
            
                for col in ['revenue', 'cogs', 'operating_income']:
                    if col in df_nvda_standard.columns:
                        df_nvda_standard[col] = (pd.to_numeric(df_nvda_standard[col], errors='coerce') / 1_000_000).round(2)

                upsert_sql = """
                INSERT INTO financial_reports (ticker, fiscal_quarter, revenue, cogs, operating_income)
                VALUES (:ticker, :fiscal_quarter, :revenue, :cogs, :operating_income)
                ON DUPLICATE KEY UPDATE revenue=VALUES(revenue), cogs=VALUES(cogs), operating_income=VALUES(operating_income);
                """
                records = df_nvda_standard[['ticker', 'fiscal_quarter', 'revenue', 'cogs', 'operating_income']].to_dict(orient='records')
                with engine.begin() as conn:
                    for r in records:
                        conn.execute(text(upsert_sql), r)
                st.sidebar.success(" NVIDIA 數據同步成功！")
            else:
                st.sidebar.error(" 無法取得 NVIDIA 資料")
        except Exception as e:
            st.sidebar.error(f"同步發生錯誤: {e}")

st.divider()

@st.cache_data
def load_and_clean_data():
    query = "SELECT ticker, fiscal_quarter, revenue, cogs, operating_income FROM financial_reports"
    df_raw = pd.read_sql(query, engine)
    df = df_raw.copy()

    df["display_quarter"] = df["fiscal_quarter"]
    nvda_mask = df["ticker"] == "NVDA"

    # 時間對齊
    if not df[nvda_mask].empty:
        df.loc[nvda_mask, "display_quarter"] = (
            pd.to_datetime(df.loc[nvda_mask, "fiscal_quarter"]).dt.to_period("Q") - 1
        ).astype(str)

    df["operating_income"] = df["operating_income"].fillna(df["revenue"] - df["cogs"])
    return df

try:
    df_clean = load_and_clean_data()
    all_companies = df_clean["ticker"].unique().tolist()
    
    selected_companies = st.sidebar.multiselect(
        "請選擇要對比的廠商：", options=all_companies, default=all_companies
    )
    df_filtered = df_clean[df_clean["ticker"].isin(selected_companies)]

    st.subheader("📈 產業利潤池結構變化")
    if not df_filtered.empty:
        fig = px.bar(
            df_filtered, x="display_quarter", y="operating_income", color="ticker",
            title="各季度供應鏈總利潤分配份額", barmode="stack"
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning("請在左側控制面板至少勾選一家公司。")

    st.divider()
    st.subheader("🧾 核心財務數據明細")
    st.dataframe(
        df_filtered[["ticker", "display_quarter", "revenue", "operating_income"]].sort_values(by="display_quarter", ascending=False),
        hide_index=True, width="stretch"
    )
except Exception as e:
    st.error(f"啟動失敗，錯誤訊息: {e}")
