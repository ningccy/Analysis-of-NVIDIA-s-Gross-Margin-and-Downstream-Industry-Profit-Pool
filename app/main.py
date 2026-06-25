import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from sqlalchemy import create_engine, text
import plotly.express as px
from dotenv import load_dotenv
from FinMind.data import DataLoader

st.set_page_config(page_title="AI 供應鏈利潤池看板", layout="wide")
load_dotenv()


@st.cache_resource
def get_db_engine():
    try:
        db_config = st.secrets["tidb"]
    except Exception:
        raise FileNotFoundError(
            "無法讀取 Streamlit Secrets，請確認專案根目錄下存在 .streamlit/secrets.toml"
        )

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
            upsert_sql = """
            INSERT INTO financial_reports (ticker, fiscal_quarter, revenue, cogs, operating_income)
            VALUES (:ticker, :fiscal_quarter, :revenue, :cogs, :operating_income)
            ON DUPLICATE KEY UPDATE 
                revenue=VALUES(revenue), 
                cogs=VALUES(cogs), 
                operating_income=VALUES(operating_income);
            """

            nvda = yf.Ticker("NVDA")
            df_nvda_raw = nvda.quarterly_financials
            if not df_nvda_raw.empty:
                df_nvda = df_nvda_raw.T
                df_nvda.index = pd.to_datetime(df_nvda.index)
                df_nvda['fiscal_quarter'] = df_nvda.index.to_period('Q').astype(str)
                df_nvda_standard = df_nvda.rename(columns={
                    'Total Revenue': 'revenue',
                    'Cost Of Revenue': 'cogs',
                    'Operating Income': 'operating_income'
                })
                df_nvda_standard['ticker'] = 'NVDA'

                for col in ['revenue', 'cogs', 'operating_income']:
                    if col in df_nvda_standard.columns:
                        df_nvda_standard[col] = (
                            pd.to_numeric(df_nvda_standard[col], errors='coerce') / 1_000_000
                        ).round(2)

                records_nvda = df_nvda_standard[
                    ['ticker', 'fiscal_quarter', 'revenue', 'cogs', 'operating_income']
                ].to_dict(orient='records')
                with engine.begin() as conn:
                    for r in records_nvda:
                        conn.execute(text(upsert_sql), r)
                st.sidebar.success("✅ NVIDIA 美股數據同步成功！")
            else:
                st.sidebar.error("❌ 無法取得 NVIDIA 資料")

            try:
                response = requests.get("https://open.er-api.com/v6/latest/USD").json()
                twd_to_usd_rate = 1 / response['rates']['TWD']
            except Exception:
                twd_to_usd_rate = 1 / 32.5

            api = DataLoader()

            target_companies = {'3017': '3017.TW', '2382': '2382.TW', '2357': '2357.TW'}
            tw_success_count = 0

            for stock_id, ticker_name in target_companies.items():
                df_tw_raw = api.taiwan_stock_financial_statement(stock_id=stock_id, start_date="2023-01-01")
                if df_tw_raw.empty:
                    continue

                df_filtered = df_tw_raw[
                    df_tw_raw['type'].isin(['Revenue', 'CostOfGoodsSold', 'OperatingIncome'])
                ].copy()
                if df_filtered.empty:
                    continue

                df_pivot = df_filtered.pivot(index='date', columns='type', values='value')
                df_standard = df_pivot.rename(columns={
                    'Revenue': 'revenue',
                    'CostOfGoodsSold': 'cogs',
                    'OperatingIncome': 'operating_income'
                })
                df_standard.index = pd.to_datetime(df_standard.index)
                df_standard['fiscal_quarter'] = df_standard.index.to_period('Q').astype(str)
                df_standard['ticker'] = ticker_name

                for col in ['revenue', 'cogs', 'operating_income']:
                    if col in df_standard.columns:
                        df_standard[col] = pd.to_numeric(df_standard[col], errors='coerce')
                        df_standard[col] = ((df_standard[col] * twd_to_usd_rate) / 1_000_000).round(2)

                records_tw = df_standard[
                    ['ticker', 'fiscal_quarter', 'revenue', 'cogs', 'operating_income']
                ].dropna(subset=['revenue']).to_dict(orient='records')
                with engine.begin() as conn:
                    for r in records_tw:
                        for k, v in r.items():
                            if pd.isna(v):
                                r[k] = None
                        conn.execute(text(upsert_sql), r)
                tw_success_count += 1

            if tw_success_count > 0:
                st.sidebar.success(f"✅ 台股供應鏈 ({tw_success_count} 家) 數據同步成功！")
            else:
                st.sidebar.warning("⚠️ 台股 API 未回傳資料，可能觸發流量限制。")

        except Exception as e:
            st.sidebar.error(f"同步發生錯誤: {e}")

    st.cache_data.clear()
    st.rerun()

st.divider()

TICKER_NAME_MAP = {
    "NVDA": "NVIDIA",
    "3017.TW": "AVC 奇鋐科技",
    "2382.TW": "Quanta 廣達電腦",
    "2357.TW": "ASUS 華碩電腦",
}

@st.cache_data(show_spinner=False)
def load_and_clean_data():
    query = """
    SELECT ticker, fiscal_quarter, revenue, cogs, operating_income 
    FROM financial_reports
    WHERE ticker IN ('NVDA', '3017.TW', '2382.TW', '2357.TW')
    """
    df_raw = pd.read_sql(query, engine)
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

    return df


try:
    df_clean = load_and_clean_data()

    if df_clean.empty:
        st.info("💡 目前資料庫中沒有任何財報數據，請點擊左側控制面板的「🔄 立即從 API 同步最新財報資料」按鈕。")
    else:
        all_companies = df_clean["ticker"].unique().tolist()
        selected_companies = st.sidebar.multiselect(
            "請選擇要對比的廠商：", options=all_companies, default=all_companies
        )
        df_filtered = df_clean[df_clean["ticker"].isin(selected_companies)]

        st.subheader("📈 產業利潤池結構變化")
        if not df_filtered.empty:
            fig = px.bar(
                df_filtered, x="display_quarter", y="operating_income", color="ticker",
                title="各季度供應鏈總利潤分配份額", barmode="stack", text="ticker"
            )
            fig.update_layout(xaxis_title="時間軸 (已對齊 NVDA 財政年度)", yaxis_title="利潤規模 (USD 百萬)", height=550)
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("請在左側控制面板至少勾選一家公司。")

        st.divider()
        st.subheader("📐 毛利率 / 營益率比較")
        st.caption("觀察重點：誰的利潤率曲線跟著 NVIDIA 同步成長，誰是持平甚至下滑——這是「定價權轉嫁」最直接的證據。")
        if not df_filtered.empty:
            df_margin = df_filtered.sort_values(by="display_quarter")

            col1, col2 = st.columns(2)

            with col1:
                fig_gm = px.line(
                    df_margin, x="display_quarter", y="gross_margin_pct", color="company_name",
                    markers=True, title="毛利率趨勢 (%)"
                )
                fig_gm.update_layout(xaxis_title="財季", yaxis_title="毛利率 (%)", height=420)
                fig_gm.update_traces(hovertemplate="%{y:.2f}%")
                st.plotly_chart(fig_gm, width="stretch")

            with col2:
                fig_om = px.line(
                    df_margin, x="display_quarter", y="operating_margin_pct", color="company_name",
                    markers=True, title="營業利益率趨勢 (%)"
                )
                fig_om.update_layout(xaxis_title="財季", yaxis_title="營業利益率 (%)", height=420)
                fig_om.update_traces(hovertemplate="%{y:.2f}%")
                st.plotly_chart(fig_om, width="stretch")
        else:
            st.warning("請在左側控制面板至少勾選一家公司。")

        st.divider()
        st.subheader("🧾 核心財務數據明細")
        st.dataframe(
            df_filtered[[
                "ticker", "company_name", "display_quarter",
                "revenue", "operating_income", "gross_margin_pct", "operating_margin_pct"
            ]].sort_values(by="display_quarter", ascending=False),
            hide_index=True, width="stretch",
            column_config={
                "ticker": st.column_config.TextColumn("代號"),
                "company_name": st.column_config.TextColumn("公司名稱"),
                "display_quarter": st.column_config.TextColumn("財季"),
                "revenue": st.column_config.NumberColumn("營收 (USD 百萬)", format="%,.2f"),
                "operating_income": st.column_config.NumberColumn("營業利益 (USD 百萬)", format="%,.2f"),
                "gross_margin_pct": st.column_config.NumberColumn("毛利率 (%)", format="%.2f%%"),
                "operating_margin_pct": st.column_config.NumberColumn("營益率 (%)", format="%.2f%%"),
            }
        )
except Exception as e:
    st.error(f"啟動失敗，錯誤訊息: {e}")
