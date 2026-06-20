import pandas as pd
from FinMind.data import DataLoader
from sqlalchemy import create_engine, text
import streamlit as st
import requests
import os

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

try:
    db_config = st.secrets["tidb"]
except Exception:
    raise FileNotFoundError(
        "無法讀取 Streamlit Secrets，請確認專案根目錄下存在 .streamlit/secrets.toml"
    )
##--------
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
    
        df_raw = api.taiwan_stock_financial_statements(
            stock_id=stock_id,
            start_date=start_date
        )
    
        if df_raw.empty:
                print(f"無法取得 {stock_id} 的資料")
                continue
        
        mops_mapping = {
              'Revenue': 'revenue',      
              'CostOfGoodsSold': 'cogs',
              'GrossProfitFromOperations': 'gross_profit',
              'OperatingIncome': 'operating_income'
          }
          
        df_filtered = df_raw[df_raw['type'].isin(mops_mapping.keys())].copy()
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
            
        final_cols = ['ticker', 'company_name', 'tier', 'fiscal_quarter', 'revenue', 'cogs', 'gross_profit', 'operating_income']
        df_final = df_standard[final_cols].dropna(subset=['revenue'])
        
        all_cleaned_records.append(df_final)
        print(f" {info['name']} 清洗完成，以百萬美元為單位。")

if all_cleaned_records:
    df_all_tw = pd.concat(all_cleaned_records)
else:
    print(" 沒有任何台股資料被成功清洗。")
    exit()
print(f"\n 開始將台股供應鏈數據寫入TiDB [{DB_NAME}]...")

upsert_sql = """
INSERT INTO financial_reports 
(ticker, company_name, tier, fiscal_quarter, revenue, cogs, gross_profit, operating_income)
VALUES (:ticker, :company_name, :tier, :fiscal_quarter, :revenue, :cogs, :gross_profit, :operating_income)
ON DUPLICATE KEY UPDATE
    revenue = VALUES(revenue),
    cogs = VALUES(cogs),
    gross_profit = VALUES(gross_profit),
    operating_income = VALUES(operating_income);
"""

records = df_all_tw.to_dict(orient='records')
with engine.begin() as connection:
    for record in records:
        for k, v in record.items():
            if pd.isna(v):
                record[k] = None
        connection.execute(text(upsert_sql), record)

print(" 奇鋐、廣達、華碩之財報數據已成功標準化並匯入TiDB")
