# agent/tools/fundamentals_fmp.py
import os, requests
def fundamentals_fmp(args):
    sym = args.get("ticker","AAPL")
    key = os.getenv("FMP_API_KEY")
    base = "https://financialmodelingprep.com/api/v3"
    r = requests.get(f"{base}/profile/{sym}", params={"apikey": key}, timeout=30).json()
    prof = r[0] if r else {}
    return {"ticker": sym, "fundamentals": {
        "pe": prof.get("pe"),
        "pb": prof.get("priceToBook"),
        "roa": prof.get("returnOnAssetsTTM"),
        "roe": prof.get("returnOnEquityTTM"),
        "marketCap": prof.get("mktCap"),
        "sector": prof.get("sector"),
        "companyName": prof.get("companyName")
    }}
