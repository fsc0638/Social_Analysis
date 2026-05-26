"""Streamlit dashboard。執行: streamlit run social_analysis/dashboard/app.py"""
import streamlit as st
import pandas as pd
import plotly.express as px

from social_analysis.storage import init_db, fetch_analyses_joined
from social_analysis.analysis import compute_trends

st.set_page_config(page_title="Social Analysis", layout="wide")
init_db()

st.title("📊 跨平台社群輿情分析")

df_all = fetch_analyses_joined()
if df_all.empty:
    st.info("資料庫尚無資料。請先執行 `python -m social_analysis.cli collect --keyword <kw>`")
    st.stop()

keywords = sorted(df_all["keyword"].dropna().unique().tolist())
keyword = st.sidebar.selectbox("關鍵字", ["(全部)"] + keywords)
df = df_all if keyword == "(全部)" else df_all[df_all["keyword"] == keyword]

trends = compute_trends(df)

c1, c2, c3, c4 = st.columns(4)
c1.metric("總貼文數", trends["total"])
c2.metric("平均情感", f"{trends['avg_sentiment']:.2f}")
c3.metric("正面比例", f"{trends['sentiment_dist'].get('positive', 0) / max(trends['total'], 1):.0%}")
c4.metric("平台數", len(trends["platform_dist"]))

st.subheader("時序熱度")
by_day = pd.DataFrame(trends["by_day"])
if not by_day.empty:
    st.plotly_chart(px.line(by_day, x="created_at", y=["posts", "engagement"]),
                    use_container_width=True)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("情感分布")
    sent_df = pd.DataFrame(list(trends["sentiment_dist"].items()), columns=["sentiment", "count"])
    st.plotly_chart(px.pie(sent_df, names="sentiment", values="count"), use_container_width=True)
with col_b:
    st.subheader("平台分布")
    plat_df = pd.DataFrame(list(trends["platform_dist"].items()), columns=["platform", "count"])
    st.plotly_chart(px.bar(plat_df, x="platform", y="count"), use_container_width=True)

st.subheader("熱門主題 Top 10")
topics_df = pd.DataFrame(trends["top_topics"], columns=["topic", "count"])
if not topics_df.empty:
    st.plotly_chart(px.bar(topics_df, x="topic", y="count"), use_container_width=True)

st.subheader("高互動貼文")
st.dataframe(pd.DataFrame(trends["top_posts"]), use_container_width=True)

with st.expander("原始資料"):
    st.dataframe(df, use_container_width=True)
