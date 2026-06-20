import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
import numpy as np
import streamlit as st

def get_db_engine():
    try:
        db_config = st.secrets["tidb"]
    except Exception:
        raise FileNotFoundError(
            " 無法讀取 Streamlit Secrets！請確認存在 .streamlit/secrets.toml"
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

print(" 開始抓取 NVIDIA 財報數據...")
nvda = yf.Ticker("NVDA")
df_raw = nvda.quarterly_financials

if df_raw.empty:
    print(" 無法取得資料，請檢查網路連線或 Ticker 是否正確！")
    exit()
print(" 資料讀取成功，開始進行清理與標準化...")

##-------------------------------------------
df = df_raw.T
df.index = pd.to_datetime(df.index)
df['fiscal_quarter'] = df.index.to_period('Q').astype(str)

required_columns = {
    'Total Revenue': 'revenue',
    'Cost Of Revenue': 'cogs',
    'Operating Income': 'operating_income'
}

for col in required_columns.keys():
    if col not in df.columns:
        df[col] = np.nan

df_cleaned = df.rename(columns=required_columns)
df_cleaned['gross_profit'] = df_cleaned['revenue'] - df_cleaned['cogs']
df_cleaned['ticker'] = 'NVDA'
df_cleaned['company_name'] = 'NVIDIA Corporation'
df_cleaned['tier'] = 'Upstream' 

final_cols = ['ticker', 'company_name', 'tier', 'fiscal_quarter', 'revenue', 'cogs', 'gross_profit', 'operating_income']
df_to_load = df_cleaned[final_cols].copy()

amount_cols = ['revenue', 'cogs', 'gross_profit', 'operating_income']
for col in amount_cols:
    df_to_load[col] = (df_to_load[col] / 1_000_000).round(2)

print("\n 資料清洗完成：")
print(df_to_load)
print("\n 開始寫入 TiDB 雲端資料庫表格 [financial_reports]...")

upsert_sql = """
INSERT INTO financial_reports 
(ticker, fiscal_quarter, revenue, cogs, operating_income)
VALUES (:ticker, :fiscal_quarter, :revenue, :cogs, :operating_income)
ON DUPLICATE KEY UPDATE
    revenue = VALUES(revenue),
    cogs = VALUES(cogs),
    operating_income = VALUES(operating_income);
"""

records = df_to_load.to_dict(orient='records')
with engine.begin() as connection:
    for record in records:
        for k, v in record.items():
            if pd.isna(v):
                record[k] = None
        
        connection.execute(text(upsert_sql), record)

print(" 成功！NVIDIA 後端數據已與台股供應鏈併入同一張表，看板隨時可以讀取！")
