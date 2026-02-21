# agent/tools/fred.py
import os, requests, pandas as pd
def fred_series(args):
    series = args.get("series_id","CPIAUCSL")
    key = os.getenv("FRED_API_KEY")
    url = "https://api.stlouisfed.org/fred/series/observations"
    r = requests.get(url, params={"api_key":key,"series_id":series,"file_type":"json"}, timeout=30).json()
    obs = r.get("observations", [])
    df = pd.DataFrame(obs)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return {"series": series, "last": df.dropna().tail(3).to_dict(orient="records")}
