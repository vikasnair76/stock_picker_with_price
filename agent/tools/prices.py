# agent/tools/prices.py
from typing import Dict, Any
from pathlib import Path
import yaml
import pandas as pd
import numpy as np

# primary free source
import yfinance as yf

# optional adapter (Alpha Vantage) — only used if config selects it
try:
    from .prices_alpha import fetch_prices_alpha
except Exception:
    fetch_prices_alpha = None

# -----------------------------
# simple persistence cache
# -----------------------------
CACHE: Dict[str, pd.DataFrame] = {}

def _cfg() -> dict:
    """Load config/settings.yaml if present; otherwise provide sane defaults."""
    p = Path("config/settings.yaml")
    if p.exists():
        try:
            return yaml.safe_load(p.read_text()) or {}
        except Exception:
            pass
    return {"data": {"prices": "yfinance"}}

def _cache_path(ticker: str) -> Path:
    Path("data/cache").mkdir(parents=True, exist_ok=True)
    return Path(f"data/cache/{ticker}.parquet")

def _save_cache(key: str, df: pd.DataFrame) -> None:
    _cache_path(key).write_bytes(df.to_parquet(index=True))

def _load_cache_if_any(key: str) -> pd.DataFrame | None:
    p = _cache_path(key)
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            return None
    return None

# -----------------------------
# public API: fetch + indicators
# -----------------------------
def fetch_prices(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch OHLCV prices and store in in-memory + on-disk cache.
    Routes to Alpha Vantage if config.data.prices == 'alpha'; otherwise uses yfinance.
    Returns a lightweight payload for the agent/Streamlit UI.
    """
    src = (_cfg().get("data") or {}).get("prices", "yfinance")
    ticker = args.get("ticker", "AAPL").upper()
    period = args.get("period", "2y")
    interval = args.get("interval", "1d")

    # Route: Alpha Vantage adapter (already returns a dict payload)
    if src == "alpha" and fetch_prices_alpha:
        res = fetch_prices_alpha({"ticker": ticker, "period": period, "interval": interval})
        # try to hydrate in-memory cache from returned data if possible
        # Alpha adapter returns timeseries in dict form; we won't rehydrate here.
        return res

    # Default route: yfinance
    # Try existing cache first if it satisfies the period/interval (keep it simple: always refetch)
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    # Normalize columns
    df = df.rename(columns=str.lower)
    # yfinance sometimes returns empty if bad ticker/interval
    if df is None or df.empty:
        # fall back to any local cache to keep the app usable
        cached = _load_cache_if_any(ticker)
        if cached is not None and not cached.empty:
            CACHE[ticker] = cached
            head = cached.head(3).to_dict()
            return {"key": ticker, "rows": len(cached), "head": head, "note": "served from local cache"}
        return {"error": f"no data for {ticker} (check symbol/interval/period)"}

    # keep only standard columns if present
    keep_cols = [c for c in ["open", "high", "low", "close", "adj close", "volume"] if c in df.columns]
    df = df[keep_cols]
    # persist
    CACHE[ticker] = df
    _save_cache(ticker, df)

    return {
        "key": ticker,
        "rows": int(len(df)),
        "head": df.head(3).round(6).to_dict(),
        "tail": df.tail(3).round(6).to_dict(),
        "source": "yfinance",
    }

def compute_indicators(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute basic technical indicators on the most recently fetched DataFrame for `df_key`.
    If not in memory, try loading from disk cache first.
    """
    key = (args.get("df_key") or args.get("ticker") or "AAPL").upper()
    df = CACHE.get(key)

    if df is None:
        # load from disk cache if available
        cached = _load_cache_if_any(key)
        if cached is None or cached.empty:
            return {"error": f"{key} not in cache. run fetch_prices first."}
        df = cached

    out = df.copy()
    # returns
    out["ret"] = out["close"].pct_change()

    # volatility (annualized using sqrt(252))
    out["vol_30d"] = out["ret"].rolling(30).std() * (252 ** 0.5)

    # momentum
    out["mom_21d"] = out["close"] / out["close"].shift(21) - 1
    out["mom_63d"] = out["close"] / out["close"].shift(63) - 1
    out["mom_126d"] = out["close"] / out["close"].shift(126) - 1

    # moving averages
    out["sma_20"] = out["close"].rolling(20).mean()
    out["sma_50"] = out["close"].rolling(50).mean()
    out["sma_200"] = out["close"].rolling(200).mean()

    # RSI(14)
    delta = out["close"].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/14, adjust=False).mean()
    roll_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    out["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD (12,26,9)
    ema12 = out["close"].ewm(span=12, adjust=False).mean()
    ema26 = out["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = macd - signal

    # update caches
    CACHE[key] = out
    _save_cache(key, out)

    # return only metadata + last rows to keep payload light
    return {
        "key": key,
        "cols": list(out.columns),
        "last_rows": out.tail(2).round(6).to_dict(),
        "notes": "Computed indicators: ret, vol_30d, mom_21/63/126, sma_20/50/200, rsi_14, macd trio",
    }
