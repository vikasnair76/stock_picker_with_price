# agent/tools/scoring.py
from typing import Dict, Any, List, Optional
import yfinance as yf
import pandas as pd
import numpy as np

# ----------------------- helpers -----------------------

def _normalize_ticker(t: str, default_suffix: Optional[str] = None) -> str:
    """
    Return a ticker that yfinance can fetch.
    If the raw ticker fails, try appending a default suffix like '.NS' (NSE) or '.BO' (BSE).
    """
    t = (t or "").strip()
    if not t:
        return t
    if default_suffix and "." not in t:
        # try raw first; caller will fall back to suffixed
        return t
    return t

def _download_one(ticker: str, period="1y") -> pd.DataFrame:
    return yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )

def _fetch_close(ticker: str, period="1y", default_suffix: Optional[str] = None) -> pd.Series:
    """
    Robustly extract a single close series. If the raw ticker is empty or fails,
    optionally try again with default_suffix (e.g., '.NS').
    """
    tried = []
    for candidate in filter(None, [ticker, f"{ticker}{default_suffix}" if default_suffix and "." not in ticker else None]):
        tried.append(candidate)
        df = _download_one(candidate, period=period)
        if df is None or df.empty:
            continue

        # Handle both normal and MultiIndex columns robustly
        if isinstance(df.columns, pd.MultiIndex):
            # typical shape: level0 fields, level1 ticker
            if ("Close", candidate) in df.columns:
                s = df[("Close", candidate)]
            else:
                # fallback: any 'Close' at level 0
                closes = [c for c in df.columns if isinstance(c, tuple) and str(c[0]).lower() == "close"]
                s = df[closes[0]] if closes else df.iloc[:, 0]
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
        if not s.empty:
            return s

    # all attempts failed
    return pd.Series(dtype=float, name="close")

def _momentum_126d(close: pd.Series) -> Optional[float]:
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

def _vol_30d(close: pd.Series) -> Optional[float]:
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

def _get_fundamentals_safe(ticker: str) -> dict:
    """
    yfinance .info can be flaky; prefer get_info()/fast_info when available.
    We only need trailing PE and ROA proxies; be defensive and return NaNs if missing.
    """
    pe = np.nan
    roa = np.nan
    try:
        tk = yf.Ticker(ticker)
        # Try new API first
        try:
            info = tk.get_info()
        except Exception:
            info = getattr(tk, "info", {}) or {}
        # PE
        pe = _to_float(info.get("trailingPE") or info.get("trailing_pe"))
        # ROA: many tickers don't have it; keep NaN if absent
        roa = _to_float(info.get("returnOnAssets") or info.get("return_on_assets"))
    except Exception:
        pass
    return {"trailingPE": pe, "returnOnAssets": roa}

# ----------------------- main tool -----------------------

def score_universe(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Args expected:
      - tickers: List[str]  (REQUIRED; no hard-coded defaults)
      - weights: Dict[str, float] with keys: momentum_126d, value_pe, quality_roa (optional)
      - period: str like '1y' (optional, default '1y')
      - default_suffix: str like '.NS' to try if raw ticker fails (optional)
    """
    tickers: List[str] = args.get("tickers") or []
    weights: Dict[str, float] = args.get("weights") or {
        "momentum_126d": 0.5,
        "value_pe": 0.25,
        "quality_roa": 0.25,
    }
    period: str = args.get("period") or "1y"
    default_suffix: Optional[str] = args.get("default_suffix")

    if not tickers or not isinstance(tickers, list):
        return {
            "table": [],
            "warning": "No tickers provided. Pass a non-empty list in 'tickers'.",
        }

    rows = []
    for raw in tickers:
        t = _normalize_ticker(str(raw).upper().strip(), default_suffix=default_suffix)

        # Prices & factors
        close = _fetch_close(t, period=period, default_suffix=default_suffix)
        mom = _momentum_126d(close) if not close.empty else None
        vol = _vol_30d(close) if not close.empty else None

        # Fundamentals (defensive)
        finfo = _get_fundamentals_safe(t)
        pe = _to_float(finfo.get("trailingPE"))
        roa = _to_float(finfo.get("returnOnAssets"))
        inv_pe = (1.0 / pe) if pd.notna(pe) and pe not in (0.0, np.inf, -np.inf) else np.nan

        rows.append({
            "ticker": t,
            "momentum_126d": mom,
            "volatility_30d": vol,
            "value_pe": inv_pe,       # higher is cheaper
            "quality_roa": roa,
        })

    df = pd.DataFrame(rows)

    # Coerce numeric & drop rows missing any required factor
    factor_cols = ["momentum_126d", "value_pe", "quality_roa"]
    for c in factor_cols + ["volatility_30d"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    valid = df.dropna(subset=factor_cols).copy()

    if valid.empty or len(valid) < 2:
        return {
            "table": df.round(4).to_dict(orient="records"),
            "warning": "Not enough valid data to score (need ≥ 2 tickers with numeric factors).",
        }

    # Z-scores (safe)
    for col in factor_cols:
        valid[col + "_z"] = _zscore_safe(valid[col])

    # Weighted score
    valid["score"] = (
        valid["momentum_126d_z"] * float(weights.get("momentum_126d", 0)) +
        valid["value_pe_z"]      * float(weights.get("value_pe", 0)) +
        valid["quality_roa_z"]   * float(weights.get("quality_roa", 0))
    )

    valid = valid.sort_values("score", ascending=False).reset_index(drop=True)

    # Attach any rows that were dropped (for transparency)
    dropped = df[~df["ticker"].isin(valid["ticker"])].copy()
    if not dropped.empty:
        dropped["score"] = np.nan
        dropped["reason"] = "missing required factors"
        # Merge for a full picture (scored first, then unscored)
        out = pd.concat([valid, dropped], ignore_index=True, sort=False)
    else:
        out = valid

    return {"table": out.round(4).to_dict(orient="records")}
