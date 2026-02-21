import streamlit as st
from components.ui import header
from dotenv import load_dotenv
load_dotenv()  # loads GOOGLE_API_KEY and LLM_BACKEND




header("Agentic Stock Picker", "Research assistant + backtests (educational only)")
st.page_link("pages/Screener.py", label="Screener", icon="📈")
st.page_link("pages/Agent_Chat.py", label="Agent Chat", icon="🤖")
# st.page_link("pages/Backtest.py", label="Backtest", icon="🧪")
# # st.page_link("pages/Portfolio.py", label="Portfolio", icon="💼")
st.info("Use the sidebar on each page to interact. This app is not financial advice.")

