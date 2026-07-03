import streamlit as st
import plotly.express as px
from utils import load_and_clean_data

st.title("🏭 台廠供應鏈差異分析")
st.caption("聚焦零組件、ODM、品牌 三層之間的利潤結構差異。")

df_clean = load_and_clean_data()
TW_TICKERS = ["3017.TW", "2382.TW", "2357.TW"]
df_tw = df_clean[df_clean["ticker"].isin(TW_TICKERS)].copy()

st.subheader("📊 台廠利潤池佔比分配")
fig1 = px.bar(
    df_tw, x="display_quarter", y="operating_income", color="company_name",
    barmode="stack", text="company_name",
    title="台廠三層供應鏈利潤池佔比"
)
fig1.update_layout(barnorm="percent", yaxis_title="佔台廠總利潤池比重 (%)", height=450)
st.plotly_chart(fig1, use_container_width=True)

st.subheader("📈 台廠毛利率趨勢")
fig2 = px.line(
    df_tw, x="display_quarter", y="gross_margin_pct", color="company_name", markers=True
)
fig2.update_layout(yaxis_title="毛利率 (%)", height=400)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("🔍 台廠營益率趨勢")
fig3 = px.line(
    df_tw, x="display_quarter", y="operating_margin_pct", color="company_name", markers=True
)
fig3.update_layout(yaxis_title="營益率 (%)", height=400)
st.plotly_chart(fig3, use_container_width=True)

st.subheader("⚖️ 最新季度台廠對比")
latest = df_tw["fiscal_quarter"].max()
st.dataframe(
    df_tw[df_tw["fiscal_quarter"] == latest][[
        "company_name", "revenue", "operating_income",
        "gross_margin_pct", "operating_margin_pct"
    ]].rename(columns={
        "company_name": "公司",
        "revenue": "營收 (USD 百萬)",
        "operating_income": "營業利益 (USD 百萬)",
        "gross_margin_pct": "毛利率 (%)",
        "operating_margin_pct": "營益率 (%)"
    }),
    use_container_width=True, hide_index=True
)
