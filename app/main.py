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
  HOST = "gateway01.ap-northeast-1.prod.aws.tidbcloud.com"
  PORT = "4000"
  USER = "5KntqF8ZunMNnjz.root"
  PASSWORD = "tYXheZ6gJz1HnhV9"
  DB_NAME = "industry_analysis"
  connect_arge = {"ssl":{"ssl_verify_cert": False}}
  return create_engine(
    f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}",
    connect_args = connect_args
  )
engine = get_db_engine()

st.title("📊 半導體與 AI 伺服器產業利潤池分析")
st.markdown("本看板追蹤從上游晶片（NVIDIA）到下游組裝與品牌廠的利潤分配與定價權轉嫁。")
st.divider()

st.sidebar.header("💠 控制面板")

@st.cache_data
def load_and_clean_data():
    query = "SELECT ticker, fiscal_quarter, revenue, cogs, operating_income FROM financial_reports"
    df_raw = pd.read_sql(query, engine)
    df = df_raw.copy()

    df["display_quarter"] = df["fiscal_quarter"]
    nvda_mask = df["ticker"] == "NVDA"

    df.loc[nvda_mask, "display_quarter"] = (
        pd.to_period(df.loc[nvda_mask, "fiscal_quarter"], freq="Q") - 1
    ).astype(str)

    df["operating_income"] = df["operating_income"].fillna(
        df["revenue"] - df["cogs"]
    )
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
            df_filtered,
            x="display_quarter",
            y="operating_income",
            color="ticker",
            title="各季度供應鏈總利潤分配份額",
            labels={
                "display_quarter": "對齊後季度",
                "operating_income": "營業利益 (USD)",
                "ticker": "公司代碼",
            },
            barmode="stack",
            text="ticker",
        )

        fig.update_layout(
            xaxis_title="時間軸 (已對齊 NVDA 財政年度)",
            yaxis_title="利潤規模 (Operating Income)",
            hovermode="x unified",
            height=550,
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("請在左側控制面板至少勾選一家公司。")

    st.divider()

    st.subheader("🧾 核心財務數據明細")
    st.dataframe(
        df_filtered[
            ["ticker", "display_quarter", "revenue", "operating_income"]
        ].sort_values(by="display_quarter", ascending=False),
        hide_index=True,
        use_container_width=True,
    )

    st.divider()
except Exception as e:
    st.error(f"啟動失敗，請檢查資料庫連線或資料表名稱。錯誤訊息: {e}")
