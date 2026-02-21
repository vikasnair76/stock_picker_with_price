# agent/tools/scoring.py
from typing import Dict, Any, List
import yfinance as yf
import pandas as pd
import numpy as np

def _fetch_close(ticker: str, period="1y") -> pd.Series:
    df = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        return pd.Series(dtype=float, name="close")

    # Handle both normal and MultiIndex columns robustly
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance often returns level 0 = fields, level 1 = ticker
        # try ('Close', ticker) then ('Adj Close', ticker), fall back to any 'Close'
        candidates = [c for c in df.columns if isinstance(c, tuple) and str(c[0]).lower() == "close"]
        if (("Close", ticker) in df.columns):
            s = df[("Close", ticker)]
        elif candidates:
            s = df[candidates[0]]
        elif (("Adj Close", ticker) in df.columns):
            s = df[("Adj Close", ticker)]
        else:
            # last resort: first column
            s = df.iloc[:, 0]
    else:
        cols_lower = {c.lower(): c for c in df.columns}
        if "close" in cols_lower:
            s = df[cols_lower["close"]]
        elif "adj close" in cols_lower:
            s = df[cols_lower["adj close"]]
        else:
            s = df.iloc[:, 0]

    s = pd.to_numeric(s, errors="coerce").dropna()
    s.name = "close"
    return s

def _momentum_126d(close: pd.Series) -> float | None:
    if close.size < 130 or close.isna().all():
        return None
    try:
        base = close.shift(126).iloc[-1]
        last = close.iloc[-1]
        if pd.isna(base) or base == 0:
            return None
        return float(last / base - 1)
    except Exception:
        return None

def _vol_30d(close: pd.Series) -> float | None:
    if close.size < 31:
        return None
    v = close.pct_change().rolling(30).std().iloc[-1]
    return float(v) if pd.notna(v) else None

def _to_float(x):
    try:
        return float(x)
    except Exception:
        return np.nan

def _zscore_safe(s: pd.Series) -> pd.Series:
    m = s.mean()
    sd = s.std(ddof=0)
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - m) / sd

def score_universe(args: Dict[str, Any]) -> Dict[str, Any]:
    tickers: List[str] = args.get("tickers") or ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"]
    weights: Dict[str, float] = args.get("weights") or {
        "momentum_126d": 0.5,
        "value_pe": 0.25,
        "quality_roa": 0.25
    }

    rows = []
    for t in tickers:
        t = t.upper().strip()
        try:
            info = yf.Ticker(t).info
        except Exception:
            info = {}

        close = _fetch_close(t)
        mom = _momentum_126d(close)
        vol = _vol_30d(close)

        pe  = _to_float(info.get("trailingPE"))
        roa = _to_float(info.get("returnOnAssets"))
        inv_pe = (1.0 / pe) if pd.notna(pe) and pe not in (0.0, np.inf, -np.inf) else np.nan

        rows.append({
            "ticker": t,
            "momentum_126d": mom,
            "volatility_30d": vol,
            "value_pe": inv_pe,
            "quality_roa": roa
        })

    df = pd.DataFrame(rows)

    # Coerce numeric & drop rows missing any required factor
    factor_cols = ["momentum_126d", "value_pe", "quality_roa"]
    for c in factor_cols + ["volatility_30d"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=factor_cols)

    if df.empty or len(df) < 2:
        return {
            "table": [],
            "warning": "Not enough valid data to score (need ≥ 2 tickers with numeric factors)."
        }

    # Z-scores (safe)
    for col in factor_cols:
        df[col + "_z"] = _zscore_safe(df[col])

    # Weighted score
    df["score"] = (
        df["momentum_126d_z"] * float(weights.get("momentum_126d", 0)) +
        df["value_pe_z"]      * float(weights.get("value_pe", 0)) +
        df["quality_roa_z"]   * float(weights.get("quality_roa", 0))
    )

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return {"table": df.round(4).to_dict(orient="records")}
