import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
import numpy as np

USER = "5KntqF8ZunMNnjz.root"   
PASSWORD = "tYXheZ6gJz1HnhV9"  
HOST = "127.0.0.1"     
PORT = "4000"          
DB_NAME = "industry_analysis"
engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}")

print("fetching nvidia's financial report...")
nvda = yf.Ticker("NVDA")
df_raw = nvda.quarterly_finanials

if df_raw.empty:
    print("can't found the data please check the connection and the Ticker is correct or not... ")
    exit()
print("loading success start data cleaning...")
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

df_cleaned = df.rename(columns = required_columns)
df_cleaned['gross_profit'] = df_cleaned['revenue'] - df_cleaned['cogs']
df_cleaned['ticker'] = 'NVDA'
df_cleaned['company_name'] = 'NVIDIA Corporation'
df_cleaned['tier'] = 'Upstream

final_cols = ['ticker', 'company_name', 'tier', 'fiscal_quarter', 'revenue', 'cogs', 'gross_profit', 'operating_income']
df_to_load = df_cleaned[final_cols].copy()

amount_cols = ['revenue', 'cogs', 'gross_profit', 'operating_income']
for col in amount_cols:
    df_to_load[col] = (df_to_load[col] / 1_000_000).round(2)

print("\n cleaning complete:")
print(df_to_load)
print(f"\n start write into TiDB database [{DB_NAME}]...")
##--------------------------------------
upsert_sql = """
INSERT INTO supply_chain_financials 
(ticker, company_name, tier, fiscal_quarter, revenue, cogs, gross_profit, operating_income)
VALUES (:ticker, :company_name, :tier, :fiscal_quarter, :revenue, :cogs, :gross_profit, :operating_income)
ON DUPLICATE KEY UPDATE
    revenue = VALUES(revenue),
    cogs = VALUES(cogs),
    gross_profit = VALUES(gross_profit),
    operating_income = VALUES(operating_income);
"""

records = df_to_load.to_dict(orient='records')
with engine.begin() as connection:
    for record in records:
        for k, v in record.items():
            if pd.isna(v):
                record[k] = None
        
        connection.execute(text(upsert_sql), record)

print("complete! backend data is ready!")
