import streamlit as st

st.set_page_config(page_title="半導體利潤池分析", layout="wide")

overview = st.Page("pages/overview.py", title="供應鏈總覽", icon="📈")
taiwan   = st.Page("pages/taiwan.py",   title="台廠差異分析", icon="🏭")

pg = st.navigation([overview, taiwan])
pg.run()
