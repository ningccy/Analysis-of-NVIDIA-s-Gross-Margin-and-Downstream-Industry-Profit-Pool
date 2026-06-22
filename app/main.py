import sys
import pandas as pd
from FinMind.data import DataLoader
from sqlalchemy import create_engine, text
import streamlit as st
import requests

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

def get_db_engine():
    local_connect_args = {"ssl": {"ssl_verify_cert": False}}
    return create_engine(
        f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}",
        connect_args=local_connect_args,
    )

engine = get_db_engine()

try:
    response = requests.get("https://open.er-api.com/v6/latest/USD").json()
    twd_to_usd_rate = 1 / response['rates']['TWD']
except Exception:
    twd_to_usd_rate = 1 / 32.5
print(f"當前 1 元新台幣約等於 {twd_to_usd_rate:.5f} 美元，若失敗則使用 1:32.5 作為基準")

api = DataLoader()

target_companies = {
    '3017': {'name': 'AVC (奇鋐科技)', 'tier': 'Component'},
    '2382': {'name': 'Quanta (廣達電腦)', 'tier': 'ODM'},
    '2357': {'name': 'ASUS (華碩電腦)', 'tier': 'Brand'}
}

all_cleaned_records = []
start_date = "2023-01-01"

for stock_id, info in target_companies.items():
    print(f"\n 正在擷取 {info['name']} ({stock_id}) 的綜合損益表...")

    df_raw = api.taiwan_stock_financial_statement(
        stock_id=stock_id,
        start_date=start_date
    )

    if df_raw.empty:
        print(f" 警告:無法取得 {stock_id} 的資料 (FinMind 回傳空表，可能被擋或超過限額)！")
        continue

    print(f" 成功取得 {stock_id} 原始資料共 {len(df_raw)} 筆，開始進行清洗...")

    mops_mapping = {
        'Revenue': 'revenue',
        'CostOfGoodsSold': 'cogs',
        'GrossProfitFromOperations': 'gross_profit',
        'OperatingIncome': 'operating_income'
    }

    df_filtered = df_raw[df_raw['type'].isin(mops_mapping.keys())].copy()
    if df_filtered.empty:
        print(f" 警告:篩選損益表科目後沒有符合的資料。")
        continue

    df_pivot = df_filtered.pivot(index='date', columns='type', values='value')

    for col in mops_mapping.keys():
        if col not in df_pivot.columns:
            df_pivot[col] = pd.NA

    df_standard = df_pivot.rename(columns=mops_mapping)
    df_standard.index = pd.to_datetime(df_standard.index)
    df_standard['fiscal_quarter'] = df_standard.index.to_period('Q').astype(str)
    df_standard['ticker'] = f"{stock_id}.TW"
    df_standard['company_name'] = info['name']
    df_standard['tier'] = info['tier']

    amount_cols = ['revenue', 'cogs', 'gross_profit', 'operating_income']
    for col in amount_cols:
        df_standard[col] = pd.to_numeric(df_standard[col], errors='coerce')
        df_standard[col] = ((df_standard[col] * twd_to_usd_rate) / 1_000_000).round(2)

    final_cols = ['ticker', 'fiscal_quarter', 'revenue', 'cogs', 'operating_income']
    df_final = df_standard[final_cols].dropna(subset=['revenue'])

    all_cleaned_records.append(df_final)
    print(f" {info['name']} 清洗完成，清洗後剩餘 {len(df_final)} 季度份的資料。")

if all_cleaned_records:
    df_all_tw = pd.concat(all_cleaned_records)
    print(f"\n準備寫入資料庫，總計待寫入行數: {len(df_all_tw)}")
else:
    print("\n 錯誤: 沒有任何台股資料被成功清洗，停止執行寫入。")
    sys.exit()

print(f"開始將台股供應鏈數據寫入 TiDB [{DB_NAME}]...")

upsert_sql = """
INSERT INTO financial_reports 
(ticker, fiscal_quarter, revenue, cogs, operating_income)
VALUES (:ticker, :fiscal_quarter, :revenue, :cogs, :operating_income)
ON DUPLICATE KEY UPDATE
    revenue = VALUES(revenue),
    cogs = VALUES(cogs),
    operating_income = VALUES(operating_income);
"""

records = df_all_tw.to_dict(orient='records')
success_count = 0

try:
    with engine.begin() as connection:
        for record in records:
            for k, v in record.items():
                if pd.isna(v):
                    record[k] = None
            connection.execute(text(upsert_sql), record)
            success_count += 1
    print(f"\n 寫入程序結束！成功將 {success_count} 筆記錄同步至 TiDB 中。")
except Exception as db_err:
    print(f"\n 資料庫寫入期間發生崩潰！詳細錯誤訊息:\n{db_err}")

    df["operating_income"] = df["operating_income"].fillna(df["revenue"] - df["cogs"])
    return df

try:
    df_clean = load_and_clean_data()

    if df_clean.empty:
        st.info("💡 目前資料庫中沒有任何財報數據，請點擊左側控制面板的按鈕。")
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
        st.subheader("🧾 核心財務數據明細")
        st.dataframe(
            df_filtered[["ticker", "display_quarter", "revenue", "operating_income"]].sort_values(
                by="display_quarter", ascending=False
            ),
            hide_index=True, width="stretch"
        )
except Exception as e:
    st.error(f"啟動失敗，錯誤訊息: {e}")
