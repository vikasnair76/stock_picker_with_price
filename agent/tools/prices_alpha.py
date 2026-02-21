# agent/tools/prices_alpha.py
import os, requests, pandas as pd
BASE = "https://www.alphavantage.co/query"

def fetch_prices_alpha(args):
    key = os.getenv("ALPHAVANTAGE_API_KEY")
    sym = args.get("ticker","AAPL")
    fx  = {"function":"TIME_SERIES_DAILY_ADJUSTED","symbol":sym,"outputsize":"full","apikey":key}
    r = requests.get(BASE, params=fx, timeout=30).json()
    ts = r.get("Time Series (Daily)", {})
    df = (pd.DataFrame(ts).T
          .rename(columns={"5. adjusted close":"close"})
          .astype(float)
          .sort_index())
    df.index = pd.to_datetime(df.index)
    return {"key": sym, "rows": len(df), "head": df.tail(3).to_dict()}
