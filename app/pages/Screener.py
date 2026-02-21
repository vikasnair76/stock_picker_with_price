# app/screener.py
import os, sys, re
import streamlit as st
import pandas as pd

# --- env/LLM status (optional, safe on Screener) ---
from dotenv import load_dotenv
load_dotenv()  # ensures .env is read even if home page didn't run first
import os

backend = os.getenv("LLM_BACKEND", "(unset)")
google_key = bool(os.getenv("GOOGLE_API_KEY"))
openai_key = bool(os.getenv("OPENAI_API_KEY"))





ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.tools import scoring
from agent.utils.market import get_live_price

st.set_page_config(page_title="Screener", page_icon="📊", layout="wide")
st.title("Screener")

# --- preset state (outside the form, buttons allowed here) ---
if "tickers_input" not in st.session_state:
    st.session_state.tickers_input = "AAPL, MSFT, NVDA, TSLA"  # default US set

cu, ci = st.columns(2)
if cu.button("Use US Mega-caps (AAPL, MSFT, NVDA, TSLA)"):
    st.session_state.tickers_input = "AAPL, MSFT, NVDA, TSLA"
if ci.button("Use India IT (TCS.NS, INFY.NS, WIPRO.NS, HCLTECH.NS)"):
    st.session_state.tickers_input = "TCS.NS, INFY.NS, WIPRO.NS, HCLTECH.NS"

st.divider()

def _parse_tickers(s: str) -> list[str]:
    if not s:
        return []
    toks = re.split(r"[,\s]+", s.strip())
    return [t for t in (tok.upper() for tok in toks) if t]

# --- the form (no buttons except the submit) ---
with st.form("scr_form", clear_on_submit=False):
    raw = st.text_area(
        "Tickers (comma/space/newline separated)",
        st.session_state.tickers_input,
        height=90,
        key="tickers_area",
    )

    period = st.selectbox("History window", ["6mo", "1y", "2y", "3y"], index=2)

    # Suffix to try if user omits market suffix
    market = st.selectbox("Market suffix (auto-append if missing)", ["(none)", ".NS"], index=0)
    suffix = None if market == "(none)" else ".NS"

    c1, c2, c3 = st.columns(3)
    w_mom = c1.number_input("Weight: Momentum (126d)", 0.0, 1.0, 0.35, 0.05)
    w_val = c2.number_input("Weight: Value (1/PE)", 0.0, 1.0, 0.25, 0.05)
    w_qlt = c3.number_input("Weight: Quality (ROA)", 0.0, 1.0, 0.40, 0.05)

    submitted = st.form_submit_button("Score Universe", use_container_width=True)

st.divider()

if submitted:
    tickers = _parse_tickers(st.session_state.tickers_area)
    if not tickers or len(tickers) < 2:
        st.warning("Please enter at least two tickers.")
        st.stop()

    weights = {"momentum_126d": w_mom, "value_pe": w_val, "quality_roa": w_qlt}
    res = scoring.score_universe({
        "tickers": tickers,
        "weights": weights,
        "period": period,
        "default_suffix": suffix,   # helpful for IN tickers if user omits suffix
    })

    table = res.get("table", [])
    warning = res.get("warning")
    if warning:
        st.info(warning)
    if not table:
        st.warning("No results.")
        st.stop()

    df = pd.DataFrame(table)

    # Add live prices (use the chosen suffix, not hard-coded)
    with st.spinner("Fetching current prices..."):
        prices = []
        for t in df["ticker"]:
            prices.append(get_live_price(t, default_suffix=suffix))
        df.insert(1, "current_price", prices)

    # Pretty names
    rename = {
        "momentum_126d": "Momentum 6m",
        "volatility_30d": "Vol 30d",
        "value_pe": "Value (1/PE)",
        "quality_roa": "Quality (ROA)",
        "score": "Composite Score",
        "current_price": "Current Price",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    st.dataframe(df, use_container_width=True)

    top = df.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Top Ticker", str(top["ticker"]))
    if "Current Price" in df.columns:
        c2.metric("Current Price", f'{(top["Current Price"] or 0):.2f}')
    if "Composite Score" in df.columns:
        c3.metric("Top Score", f'{top["Composite Score"]:.3f}')

    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="screener_results.csv",
        use_container_width=True,
    )
