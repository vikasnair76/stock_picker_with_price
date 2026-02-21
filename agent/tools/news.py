from typing import Dict, Any
import yfinance as yf
from datetime import datetime, timedelta

def get_news(args: Dict[str, Any]) -> Dict[str, Any]:
    ticker = args.get("ticker","AAPL")
    days = int(args.get("days",7))
    items = yf.Ticker(ticker).news or []
    cutoff = datetime.utcnow() - timedelta(days=days)
    out = []
    for it in items[:50]:
        ts = datetime.utcfromtimestamp(it.get("providerPublishTime",0))
        if ts >= cutoff:
            out.append({"title": it.get("title"), "link": it.get("link"), "publisher": it.get("publisher"), "time": ts.isoformat()})
    return {"ticker": ticker, "news": out[:10]}
