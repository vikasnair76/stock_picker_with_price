# routes fundamentals to yfinance or FMP based on config
import yaml, os
from pathlib import Path
from typing import Dict, Any
import yfinance as yf

# optional imports
try:
    from .fundamentals_fmp import fundamentals_fmp
except Exception:
    fundamentals_fmp = None

def _cfg():
    p = Path("config/settings.yaml")
    return yaml.safe_load(p.read_text()) if p.exists() else {"data":{"fundamentals":"yfinance"}}

def get_fundamentals(args: Dict[str, Any]) -> Dict[str, Any]:
    ticker = args.get("ticker", "AAPL")
    src = (_cfg().get("data") or {}).get("fundamentals", "yfinance")
    if src == "fmp" and fundamentals_fmp:
        return fundamentals_fmp({"ticker": ticker})
    # fallback: yfinance
    info = yf.Ticker(ticker).info
    keep = {k: info.get(k) for k in ["trailingPE","forwardPE","priceToBook","returnOnAssets","returnOnEquity","marketCap","sector","shortName"]}
    return {"ticker": ticker, "fundamentals": keep}
