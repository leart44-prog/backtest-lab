"""Earnings-gap event detection and PEAD trade simulation.

Trigger: Day-1 open is >= gap_pct above Day-0 close.
Entry:   Day-1 close (matches the retail "long-after-breakout-candle" pattern).
Stop:    Day-1 low.
Trail:   10-day SMA after day 5, 20-day SMA after day 30.
Exit:    Stop hit | weekly-close < 50-EMA | day 60 (forced).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    initial_stop: float
    gap_pct: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str  # "stop", "ema50_break", "max_days", "end_of_data"
    days_held: int
    return_pct: float
    mae_pct: float  # max adverse excursion
    mfe_pct: float  # max favourable excursion


def find_gap_events(df: pd.DataFrame, gap_pct: float = 0.05, min_price: float = 5.0) -> pd.DataFrame:
    """Return rows where today's open gapped >= gap_pct above yesterday's close."""
    if df.empty or len(df) < 2:
        return df.iloc[0:0]
    prev_close = df["Close"].shift(1)
    gap = (df["Open"] - prev_close) / prev_close
    mask = (gap >= gap_pct) & (df["Open"] >= min_price) & prev_close.notna()
    events = df.loc[mask].copy()
    events["gap_pct"] = gap.loc[mask]
    return events


def simulate_trade(
    ticker: str,
    df: pd.DataFrame,
    entry_idx: int,
    gap_pct: float,
    max_days: int = 60,
    sma_short: int = 10,
    sma_long: int = 20,
    ema_emergency: int = 50,
) -> Trade | None:
    """Simulate one PEAD trade from the gap day forward."""
    if entry_idx >= len(df) - 1:
        return None

    row = df.iloc[entry_idx]
    entry_date = df.index[entry_idx]
    entry_price = float(row["Close"])
    initial_stop = float(row["Low"])
    if not np.isfinite(entry_price) or not np.isfinite(initial_stop) or entry_price <= initial_stop:
        return None

    close = df["Close"]
    sma_s = close.rolling(sma_short).mean()
    sma_l = close.rolling(sma_long).mean()
    ema_em = close.ewm(span=ema_emergency, adjust=False).mean()

    high_water = entry_price
    low_water = entry_price
    exit_reason = "end_of_data"
    exit_idx = min(entry_idx + max_days, len(df) - 1)

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

        if k < 5:
            stop = initial_stop
        elif k < 30:
            stop = max(initial_stop, float(sma_s.iloc[i - 1]) if np.isfinite(sma_s.iloc[i - 1]) else initial_stop)
        else:
            stop = max(initial_stop, float(sma_l.iloc[i - 1]) if np.isfinite(sma_l.iloc[i - 1]) else initial_stop)

        if bar_low <= stop:
            exit_idx = i
            exit_price = stop  # assume stop fills at level (intraday-touch)
            exit_reason = "stop"
            break

        if k % 5 == 0 and np.isfinite(ema_em.iloc[i]):
            if bar_close < float(ema_em.iloc[i]):
                exit_idx = i
                exit_price = bar_close
                exit_reason = "ema50_break"
                break
    else:
        exit_idx = entry_idx + max_days
        if exit_idx >= len(df):
            exit_idx = len(df) - 1
        exit_price = float(df.iloc[exit_idx]["Close"])
        exit_reason = "max_days"

    if exit_reason == "end_of_data":
        exit_price = float(df.iloc[exit_idx]["Close"])

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


def run_ticker(
    ticker: str,
    df: pd.DataFrame,
    gap_pct: float = 0.05,
    max_days: int = 60,
) -> list[Trade]:
    """Find all gap events on a ticker and simulate trades for each."""
    events = find_gap_events(df, gap_pct=gap_pct)
    trades: list[Trade] = []
    last_exit = -1
    for ev_date in events.index:
        i = df.index.get_loc(ev_date)
        if i <= last_exit:
            continue  # no overlapping trades
        ev_gap = float(events.loc[ev_date, "gap_pct"])
        t = simulate_trade(ticker, df, i, ev_gap, max_days=max_days)
        if t is None:
            continue
        trades.append(t)
        last_exit = df.index.get_loc(t.exit_date)
    return trades
