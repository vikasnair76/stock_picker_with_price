import streamlit as st

def header(title: str, subtitle: str = ""):
    st.set_page_config(page_title=title, page_icon="📊", layout="wide")
    st.title(title)
    if subtitle:
        st.caption(subtitle)

def metric_row(metrics: dict):
    cols = st.columns(len(metrics))
    for c,(k,v) in zip(cols, metrics.items()):
        c.metric(k, v)
