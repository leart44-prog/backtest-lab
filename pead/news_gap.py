"""News-gap variant of the PEAD strategy.

Designed for non-earnings catalysts: contract wins, FDA approvals, M&A
target news, index inclusions, top-tier analyst initiations. Differs
from the earnings variant in five ways:

  1. Higher gap threshold (+8% vs +5%) — filters cosmetic news
  2. Mandatory volume confirmation (>= 3x 20d avg) — institutional bid
  3. Tighter initial stop (midpoint of Day-1 range, not full low)
  4. Faster trail schedule (5-SMA day 3, 10-SMA day 15)
  5. Shorter max hold (25 days vs 60) — news cascades expire faster

These parameters reflect the empirical reality that news-driven gaps
cascade through analyst revisions and ETF mechanics more weakly and
more briefly than earnings beats.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .signals import Trade


def find_news_gap_events(
    df: pd.DataFrame,
    gap_pct: float = 0.08,
    vol_mult: float = 3.0,
    avg_vol_window: int = 20,
    min_price: float = 5.0,
) -> pd.DataFrame:
    """Detect gap + volume-surge candidates."""
    if df.empty or len(df) < avg_vol_window + 2:
        return df.iloc[0:0]
    prev_close = df["Close"].shift(1)
    gap = (df["Open"] - prev_close) / prev_close
    avg_vol = df["Volume"].rolling(avg_vol_window).mean().shift(1)
    vol_ratio = df["Volume"] / avg_vol
    mask = (
        (gap >= gap_pct)
        & (vol_ratio >= vol_mult)
        & (df["Open"] >= min_price)
        & prev_close.notna()
        & avg_vol.notna()
    )
    events = df.loc[mask].copy()
    events["gap_pct"] = gap.loc[mask]
    events["vol_ratio"] = vol_ratio.loc[mask]
    return events


def simulate_news_trade(
    ticker: str,
    df: pd.DataFrame,
    entry_idx: int,
    gap_pct: float,
    max_days: int = 25,
    sma_short: int = 5,
    sma_long: int = 10,
    ema_emergency: int = 21,
) -> Trade | None:
    """News-gap trade with tighter stop and faster trail."""
    if entry_idx >= len(df) - 1:
        return None

    row = df.iloc[entry_idx]
    entry_date = df.index[entry_idx]
    entry_price = float(row["Close"])
    day_high = float(row["High"])
    day_low = float(row["Low"])

    # Tighter initial stop: midpoint of Day-1 range (capped slightly below entry)
    range_mid = day_low + 0.5 * (day_high - day_low)
    initial_stop = min(entry_price * 0.985, range_mid)
    if not np.isfinite(entry_price) or initial_stop >= entry_price:
        return None

    close = df["Close"]
    sma_s = close.rolling(sma_short).mean()
    sma_l = close.rolling(sma_long).mean()
    ema_em = close.ewm(span=ema_emergency, adjust=False).mean()

    high_water = entry_price
    low_water = entry_price
    exit_reason = "end_of_data"
    exit_idx = min(entry_idx + max_days, len(df) - 1)
    exit_price = float(df.iloc[exit_idx]["Close"])

    for k in range(1, max_days + 1):
        i = entry_idx + k
        if i >= len(df):
            break

        bar = df.iloc[i]
        bar_high = float(bar["High"])
        bar_low = float(bar["Low"])
        bar_close = float(bar["Close"])

        high_water = max(high_water, bar_high)
        low_water = min(low_water, bar_low)

        if k < 3:
            stop = initial_stop
        elif k < 15:
            stop = max(initial_stop, float(sma_s.iloc[i - 1]) if np.isfinite(sma_s.iloc[i - 1]) else initial_stop)
        else:
            stop = max(initial_stop, float(sma_l.iloc[i - 1]) if np.isfinite(sma_l.iloc[i - 1]) else initial_stop)

        if bar_low <= stop:
            exit_idx = i
            exit_price = stop
            exit_reason = "stop"
            break

        if k % 3 == 0 and np.isfinite(ema_em.iloc[i]):
            if bar_close < float(ema_em.iloc[i]):
                exit_idx = i
                exit_price = bar_close
                exit_reason = "ema21_break"
                break
    else:
        exit_idx = entry_idx + max_days
        if exit_idx >= len(df):
            exit_idx = len(df) - 1
        exit_price = float(df.iloc[exit_idx]["Close"])
        exit_reason = "max_days"

    ret = exit_price / entry_price - 1.0
    mae = low_water / entry_price - 1.0
    mfe = high_water / entry_price - 1.0

    return Trade(
        ticker=ticker,
        entry_date=entry_date,
        entry_price=entry_price,
        initial_stop=initial_stop,
        gap_pct=float(gap_pct),
        exit_date=df.index[exit_idx],
        exit_price=exit_price,
        exit_reason=exit_reason,
        days_held=int(exit_idx - entry_idx),
        return_pct=float(ret),
        mae_pct=float(mae),
        mfe_pct=float(mfe),
    )


def run_ticker_news(
    ticker: str,
    df: pd.DataFrame,
    gap_pct: float = 0.08,
    vol_mult: float = 3.0,
    max_days: int = 25,
) -> list[Trade]:
    events = find_news_gap_events(df, gap_pct=gap_pct, vol_mult=vol_mult)
    trades: list[Trade] = []
    last_exit = -1
    for ev_date in events.index:
        i = df.index.get_loc(ev_date)
        if i <= last_exit:
            continue
        ev_gap = float(events.loc[ev_date, "gap_pct"])
        t = simulate_news_trade(ticker, df, i, ev_gap, max_days=max_days)
        if t is None:
            continue
        trades.append(t)
        last_exit = df.index.get_loc(t.exit_date)
    return trades


def run_universe_news(
    data: dict[str, pd.DataFrame],
    gap_pct: float = 0.08,
    vol_mult: float = 3.0,
    max_days: int = 25,
) -> list[Trade]:
    all_trades: list[Trade] = []
    for ticker, df in data.items():
        try:
            trades = run_ticker_news(ticker, df, gap_pct=gap_pct, vol_mult=vol_mult, max_days=max_days)
            all_trades.extend(trades)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {ticker} skipped: {exc}")
    return all_trades
