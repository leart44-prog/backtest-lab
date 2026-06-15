"""yfinance fetcher with on-disk parquet cache.

One file per ticker under data/equities/. Re-runs reuse the cache.
Set FORCE_REFRESH=1 in the environment to bypass the cache.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "equities"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace(".", "_")
    return CACHE_DIR / f"{safe}.parquet"


def fetch_one(ticker: str, years: int = 10, force: bool = False) -> pd.DataFrame:
    """Fetch daily OHLCV for one ticker. Returns DataFrame indexed by date."""
    cache = _cache_path(ticker)
    if cache.exists() and not force and os.environ.get("FORCE_REFRESH") != "1":
        try:
            df = pd.read_parquet(cache)
            if not df.empty:
                return df
        except Exception:
            pass

    import yfinance as yf

    end = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    start = end - pd.DateOffset(years=years)

    for attempt in (1, 2, 3):
        try:
            df = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {ticker} attempt {attempt} error: {exc}")
            df = pd.DataFrame()

        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.to_parquet(cache)
            return df

        if attempt < 3:
            time.sleep(5 * attempt)

    return pd.DataFrame()


def fetch_universe(tickers: list[str], years: int = 10) -> dict[str, pd.DataFrame]:
    """Fetch all tickers; returns dict ticker -> DataFrame. Empty frames skipped."""
    out: dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers, 1):
        print(f"  [{i:3d}/{len(tickers)}] {t}...", end="", flush=True)
        df = fetch_one(t, years=years)
        if df.empty:
            print(" empty")
            continue
        out[t] = df
        print(f" {len(df)} rows")
    return out
