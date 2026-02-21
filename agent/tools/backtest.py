from typing import Dict, Any, List
import yfinance as yf
import pandas as pd
import numpy as np
from .scoring import score_universe

def _download_many(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    px = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    return px.dropna(how="all").ffill()

def run_backtest(args: Dict[str, Any]) -> Dict[str, Any]:
    tickers = args.get("tickers")
    start = args.get("start","2022-01-01")
    end   = args.get("end",  None)
    n_pos = int(args.get("n_positions",5))
    reb   = int(args.get("rebalance_days",21))

    if not tickers:
        # derive from scoring default universe
        tbl = score_universe({"tickers": None})["table"]
        tickers = [row["ticker"] for row in tbl[:15]]

    px = _download_many(tickers, start, end)
    rets = px.pct_change().fillna(0)
    dates = rets.index
    equity = 1.0
    curve = []
    hold = []

    for i, dt in enumerate(dates):
        if i % reb == 0:
            # simple momentum pick: trailing 126d return
            trailing = (px.loc[:dt].iloc[-1] / px.loc[:dt].shift(126).iloc[-1] - 1).dropna()
            winners = trailing.sort_values(ascending=False).head(n_pos).index.tolist()
            hold = winners
        day_ret = rets.loc[dt, hold].mean() if hold else 0.0
        equity *= (1 + day_ret)
        curve.append({"date": dt, "equity": equity, "n": len(hold)})

    out = pd.DataFrame(curve).set_index("date")
    stats = {
        "CAGR": (equity ** (252/len(out)) - 1) if len(out) > 0 else 0,
        "MaxDrawdown": float((out["equity"]/out["equity"].cummax()-1).min()),
        "Vol": float(out["equity"].pct_change().std() * (252**0.5)),
        "Sharpe": float((out["equity"].pct_change().mean() * 252) / (out["equity"].pct_change().std() + 1e-9))
    }
    return {"summary": stats, "last_equity": equity, "curve_head": out.head(3).to_dict(), "curve_tail": out.tail(3).to_dict()}
