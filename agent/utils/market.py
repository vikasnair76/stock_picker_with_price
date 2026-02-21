# agent/utils/market.py
from __future__ import annotations
import yfinance as yf
import pandas as pd
from typing import Optional

def get_live_price(ticker: str, default_suffix: Optional[str] = ".NS") -> Optional[float]:
    """
    Try to return the most recent traded price.
    Strategy:
      1) fast_info.last_price (fastest)
      2) 1-minute bars latest close
      3) 1-day bar last close
    """
    t = ticker.strip().upper()
    tried = []
    for candidate in filter(None, [t, f"{t}{default_suffix}" if default_suffix and "." not in t else None]):
        tried.append(candidate)
        try:
            tk = yf.Ticker(candidate)
            fi = getattr(tk, "fast_info", None)
            if fi:
                p = getattr(fi, "last_price", None)
                if p and float(p) > 0:
                    return float(p)
        except Exception:
            pass
        # 1-minute recent bar
        try:
            df1 = yf.download(candidate, period="1d", interval="1m", auto_adjust=True, progress=False, threads=False)
            if df1 is not None and not df1.empty:
                v = pd.to_numeric(df1["Close"]).dropna().iloc[-1]
                return float(v)
        except Exception:
            pass
        # daily fallback
        try:
            dfD = yf.download(candidate, period="5d", interval="1d", auto_adjust=True, progress=False, threads=False)
            if dfD is not None and not dfD.empty:
                v = pd.to_numeric(dfD["Close"]).dropna().iloc[-1]
                return float(v)
        except Exception:
            pass
    return None
