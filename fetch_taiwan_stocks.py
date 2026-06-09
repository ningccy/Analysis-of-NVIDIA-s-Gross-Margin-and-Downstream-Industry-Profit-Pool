import pandas as pd
from FinMind.data import DataLoader
from sqlalchemy import create_engine, text
import requests

DB_HOST = "gateway01.ap-northeast-1.prod.aws.tidbcloud.com"
DB_PORT = "4000"
DB_USER = "5KntqF8ZunMNnjz.root"
DB_PASSWORD = ""
DB_NAME = "industry_analysis" 

engine = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}")
