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
