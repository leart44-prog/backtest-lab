#!/usr/bin/env python3
"""Volume-profile swing framework for QQQ (Alpaca market data).

Pulls hourly bars, builds monthly + weekly volume profiles (POC/VAH/VAL),
classifies trend vs. balance from stacked POCs, and prints an actionable
swing plan: bias, entry zone, stop, targets, key confluence levels.

Usage:
    pip install alpaca-py pandas numpy
    export ALPACA_API_KEY_ID=...
    export ALPACA_API_SECRET_KEY=...
    python qqq_volume_analysis.py [--symbol QQQ] [--months 12] [--feed iex|sip]

Notes:
    - Free Alpaca accounts get IEX-only volume, which is a subset of total
      tape. Profile SHAPE is still usable for swing work, but absolute
      volume numbers are low. Use --feed sip if you have a paid plan.
    - Profile is a TPO-style approximation: each bar's volume is spread
      uniformly across its high-low range. Adequate for H1+ timeframes.
"""
import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed
except ImportError:
    sys.exit("Install alpaca-py first:  pip install alpaca-py pandas numpy")


@dataclass
class Profile:
    label: str
    start: pd.Timestamp
    end: pd.Timestamp
    poc: float
    vah: float
    val: float
    high: float
    low: float
    close: float
    total_volume: float


def fetch_hourly(symbol, months_back, client, feed):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=months_back * 31)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Hour,
        start=start,
        end=end,
        adjustment="raw",
        feed=feed,
    )
    df = client.get_stock_bars(req).df
    if df.empty:
        sys.exit(f"No bars returned for {symbol}")
    df = df.reset_index()
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol]
    return df.set_index("timestamp").sort_index()[["open", "high", "low", "close", "volume"]]


def build_profile(bars, bins=80, va_pct=0.70):
    """Distribute each bar's volume uniformly across its H-L range, then
    compute POC + value area by expanding outward from POC until va_pct
    of total volume is covered."""
    if bars.empty:
        return None
    lo, hi = bars["low"].min(), bars["high"].max()
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    vols = np.zeros(bins)
    for _, r in bars.iterrows():
        bl, bh, bv = r["low"], r["high"], r["volume"]
        if bh <= bl or bv <= 0:
            continue
        s = max(0, np.searchsorted(edges, bl, side="right") - 1)
        e = min(bins - 1, np.searchsorted(edges, bh, side="right") - 1)
        n = e - s + 1
        if n > 0:
            vols[s:e + 1] += bv / n
    centers = (edges[:-1] + edges[1:]) / 2
    poc_i = int(np.argmax(vols))
    total = vols.sum()
    target = total * va_pct
    covered = vols[poc_i]
    lo_i = hi_i = poc_i
    while covered < target:
        up = vols[hi_i + 1] if hi_i + 1 < bins else -1
        dn = vols[lo_i - 1] if lo_i - 1 >= 0 else -1
        if up < 0 and dn < 0:
            break
        if up >= dn:
            hi_i += 1
            covered += up
        else:
            lo_i -= 1
            covered += dn
    return float(centers[poc_i]), float(centers[hi_i]), float(centers[lo_i]), float(total)


def period_profiles(bars, freq):
    out = []
    for ts, grp in bars.groupby(pd.Grouper(freq=freq)):
        if grp.empty:
            continue
        res = build_profile(grp)
        if res is None:
            continue
        poc, vah, val, tot = res
        label = ts.strftime("%Y-%m") if freq.startswith("M") else ts.strftime("%Y-W%V")
        out.append(Profile(
            label=label, start=grp.index[0], end=grp.index[-1],
            poc=poc, vah=vah, val=val,
            high=float(grp["high"].max()), low=float(grp["low"].min()),
            close=float(grp["close"].iloc[-1]), total_volume=tot,
        ))
    return out


def classify_trend(profiles, n=4):
    if len(profiles) < n:
        return "insufficient-data"
    pocs = [p.poc for p in profiles[-n:]]
    ups = sum(1 for a, b in zip(pocs, pocs[1:]) if b > a)
    downs = sum(1 for a, b in zip(pocs, pocs[1:]) if b < a)
    if ups >= n - 2:
        return "uptrend"
    if downs >= n - 2:
        return "downtrend"
    return "balance"


def print_plan(symbol, monthly, weekly, price):
    bar = "=" * 64
    print(f"\n{bar}\n{symbol} — Volume-Profile Swing Framework\n{bar}")
    print(f"Current price: {price:.2f}\n")

    print("Monthly profiles (last 6):")
    for p in monthly[-6:]:
        print(f"  {p.label}  POC {p.poc:8.2f}  VAH {p.vah:8.2f}  VAL {p.val:8.2f}  close {p.close:8.2f}")

    print("\nWeekly profiles (last 8):")
    for p in weekly[-8:]:
        print(f"  {p.label}  POC {p.poc:8.2f}  VAH {p.vah:8.2f}  VAL {p.val:8.2f}  close {p.close:8.2f}")

    m_trend = classify_trend(monthly, 4)
    w_trend = classify_trend(weekly, 4)
    print(f"\nMonthly structure: {m_trend}")
    print(f"Weekly  structure: {w_trend}")

    if not monthly or not weekly:
        return

    last_m, prev_m = monthly[-1], monthly[-2] if len(monthly) >= 2 else monthly[-1]
    last_w, prev_w = weekly[-1], weekly[-2] if len(weekly) >= 2 else weekly[-1]

    print("\n--- Swing plan ---")
    if m_trend == "uptrend":
        entry_hi = last_w.poc
        entry_lo = prev_m.vah if price > prev_m.vah else last_m.val
        stop = min(last_w.val, prev_w.val)
        t1 = last_m.high
        t2 = last_m.high + (last_m.high - last_m.low)
        print(f"Bias: LONG  (monthly uptrend, weekly {w_trend})")
        print(f"Entry zone: {min(entry_lo, entry_hi):.2f} – {max(entry_lo, entry_hi):.2f}  (monthly VAH + weekly POC confluence)")
        print(f"Stop:       below {stop:.2f}")
        print(f"T1:         {t1:.2f}  (recent high / breakout retest)")
        print(f"T2:         {t2:.2f}  (range extension)")
    elif m_trend == "downtrend":
        entry_lo = last_w.poc
        entry_hi = prev_m.val if price < prev_m.val else last_m.vah
        stop = max(last_w.vah, prev_w.vah)
        t1 = last_m.low
        t2 = last_m.low - (last_m.high - last_m.low)
        print(f"Bias: SHORT  (monthly downtrend, weekly {w_trend})")
        print(f"Entry zone: {min(entry_lo, entry_hi):.2f} – {max(entry_lo, entry_hi):.2f}  (monthly VAL + weekly POC confluence)")
        print(f"Stop:       above {stop:.2f}")
        print(f"T1:         {t1:.2f}")
        print(f"T2:         {t2:.2f}")
    else:
        print("Bias: NEUTRAL (balance) — fade edges, avoid POC")
        print(f"Short zone: {last_m.vah:.2f}+   Long zone: {last_m.val:.2f}-   Avoid: {last_m.poc:.2f}")

    print("\n--- Key levels (sorted) ---")
    levels = sorted({round(x, 2) for x in (
        last_m.vah, last_m.poc, last_m.val,
        prev_m.vah, prev_m.poc, prev_m.val,
        last_w.vah, last_w.poc, last_w.val,
    )})
    for lvl in levels:
        tag = "  <<< price" if abs(lvl - price) < 0.5 else ""
        print(f"  {lvl:8.2f}   ({(lvl - price) / price * 100:+.2f}%){tag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="QQQ")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--feed", choices=["iex", "sip"], default="iex")
    args = ap.parse_args()

    key = os.getenv("ALPACA_API_KEY_ID")
    sec = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not sec:
        sys.exit("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY env vars.")

    feed = DataFeed.SIP if args.feed == "sip" else DataFeed.IEX
    client = StockHistoricalDataClient(key, sec)
    bars = fetch_hourly(args.symbol, args.months, client, feed)
    print(f"Fetched {len(bars)} hourly bars for {args.symbol} "
          f"({bars.index[0].date()} – {bars.index[-1].date()}, feed={args.feed})")

    monthly = period_profiles(bars, "MS")
    weekly = period_profiles(bars, "W-MON")
    price = float(bars["close"].iloc[-1])
    print_plan(args.symbol, monthly, weekly, price)


if __name__ == "__main__":
    main()
