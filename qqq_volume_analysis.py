#!/usr/bin/env python3
"""Volume-profile swing framework for QQQ (Alpaca market data).

Subcommands:
    analyze    Current-state swing plan from latest data (default)
    backtest   Walk-forward simulation of the framework rules (reports R-metrics)
    plot       Price + monthly/weekly volume profiles (PNG output)

Usage:
    pip install -r requirements-qqq.txt
    export ALPACA_API_KEY_ID=...
    export ALPACA_API_SECRET_KEY=...

    python qqq_volume_analysis.py analyze  --symbol QQQ --months 12
    python qqq_volume_analysis.py backtest --symbol QQQ --months 24
    python qqq_volume_analysis.py plot     --symbol QQQ --months 12 --out qqq.png

Notes:
    - Free Alpaca tier returns IEX-only volume. Shape of the profile is
      still usable for swing work. Use --feed sip on paid plans.
    - Profile is a TPO-style approximation: each bar's volume spread
      uniformly across its H-L range. Adequate for H1+ timeframes.
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
    sys.exit("Install dependencies first:  pip install -r requirements-qqq.txt")


# ───────────────────── core: profile + classification ─────────────────────

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
    """Distribute each bar's volume uniformly across H-L, then expand the
    value area outward from POC until va_pct of total volume is covered."""
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
    return (
        float(centers[poc_i]),
        float(centers[hi_i]),
        float(centers[lo_i]),
        float(total),
        centers,
        vols,
    )


def period_profiles(bars, freq):
    out = []
    for ts, grp in bars.groupby(pd.Grouper(freq=freq)):
        if grp.empty:
            continue
        res = build_profile(grp)
        if res is None:
            continue
        poc, vah, val, tot, _, _ = res
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


# ───────────────────────────── analyze mode ─────────────────────────────

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
    last_m = monthly[-1]
    prev_m = monthly[-2] if len(monthly) >= 2 else last_m
    last_w = weekly[-1]
    prev_w = weekly[-2] if len(weekly) >= 2 else last_w

    print("\n--- Swing plan ---")
    if m_trend == "uptrend":
        entry_hi = last_w.poc
        entry_lo = prev_m.vah if price > prev_m.vah else last_m.val
        stop = min(last_w.val, prev_w.val)
        t1 = last_m.high
        t2 = last_m.high + (last_m.high - last_m.low)
        print(f"Bias: LONG  (monthly uptrend, weekly {w_trend})")
        print(f"Entry zone: {min(entry_lo, entry_hi):.2f} – {max(entry_lo, entry_hi):.2f}")
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
        print(f"Entry zone: {min(entry_lo, entry_hi):.2f} – {max(entry_lo, entry_hi):.2f}")
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


# ───────────────────────────── backtest mode ─────────────────────────────

def run_backtest(bars, max_hold_days=28):
    """Walk-forward: at each weekly open compute profiles using PAST data
    only, generate one trade candidate per the framework, simulate fill
    and exit within max_hold_days. No overlapping trades."""
    trades = []
    cooldown_until = None
    week_starts = pd.date_range(
        bars.index[0].normalize(), bars.index[-1].normalize(), freq="W-MON", tz=bars.index.tz,
    )

    for wk_start in week_starts:
        if cooldown_until is not None and wk_start < cooldown_until:
            continue
        past = bars[bars.index < wk_start]
        if len(past) < 30 * 24:
            continue
        monthly = period_profiles(past, "MS")
        weekly = period_profiles(past, "W-MON")
        if len(monthly) < 3 or len(weekly) < 4:
            continue
        trend = classify_trend(monthly, 4)
        if trend not in ("uptrend", "downtrend"):
            continue

        last_m = monthly[-1]
        prev_m = monthly[-2]
        last_w = weekly[-1]
        prev_w = weekly[-2]

        if trend == "uptrend":
            direction = 1
            entry = last_m.vah
            stop = min(last_w.val, prev_w.val)
            t1 = max(last_m.high, prev_m.high)
            t2 = t1 + (last_m.high - last_m.low)
        else:
            direction = -1
            entry = last_m.val
            stop = max(last_w.vah, prev_w.vah)
            t1 = min(last_m.low, prev_m.low)
            t2 = t1 - (last_m.high - last_m.low)

        if direction * (t1 - entry) <= 0 or direction * (entry - stop) <= 0:
            continue  # invalid geometry

        window = bars[
            (bars.index >= wk_start)
            & (bars.index < wk_start + pd.Timedelta(days=max_hold_days))
        ]
        if window.empty:
            continue

        filled_ts = None
        for ts, row in window.iterrows():
            if row["low"] <= entry <= row["high"]:
                filled_ts = ts
                break
        if filled_ts is None:
            continue

        remaining = window[window.index > filled_ts]
        exit_ts, exit_px, reason = None, None, "timeout"
        trailing_stop = stop
        hit_t1 = False
        for ts, row in remaining.iterrows():
            if direction == 1:
                if row["low"] <= trailing_stop:
                    exit_ts, exit_px = ts, trailing_stop
                    reason = "be" if hit_t1 else "stop"
                    break
                if not hit_t1 and row["high"] >= t1:
                    hit_t1 = True
                    trailing_stop = entry
                if row["high"] >= t2:
                    exit_ts, exit_px, reason = ts, t2, "target"
                    break
            else:
                if row["high"] >= trailing_stop:
                    exit_ts, exit_px = ts, trailing_stop
                    reason = "be" if hit_t1 else "stop"
                    break
                if not hit_t1 and row["low"] <= t1:
                    hit_t1 = True
                    trailing_stop = entry
                if row["low"] <= t2:
                    exit_ts, exit_px, reason = ts, t2, "target"
                    break
        if exit_ts is None:
            exit_ts = remaining.index[-1] if not remaining.empty else filled_ts
            exit_px = float(window["close"].iloc[-1])

        risk = abs(entry - stop)
        pnl = direction * (exit_px - entry)
        r = pnl / risk if risk > 0 else 0.0
        trades.append({
            "entry_time": filled_ts, "exit_time": exit_ts,
            "dir": "L" if direction == 1 else "S",
            "entry": round(entry, 2), "stop": round(stop, 2),
            "t1": round(t1, 2), "t2": round(t2, 2),
            "exit": round(exit_px, 2),
            "reason": reason, "r": round(r, 2),
        })
        cooldown_until = exit_ts

    return pd.DataFrame(trades)


def print_backtest(df):
    if df.empty:
        print("\nNo trades generated.")
        return
    wins = df[df["r"] > 0]
    losses = df[df["r"] <= 0]
    equity = df["r"].cumsum()
    dd = (equity - equity.cummax()).min()
    print(f"\n--- Backtest results ({df['entry_time'].iloc[0].date()} → {df['exit_time'].iloc[-1].date()}) ---")
    print(f"Trades:            {len(df)}  ({len(df[df['dir']=='L'])} long / {len(df[df['dir']=='S'])} short)")
    print(f"Win rate:          {len(wins) / len(df) * 100:.1f}%")
    print(f"Avg R:             {df['r'].mean():.2f}")
    print(f"Total R:           {df['r'].sum():.1f}")
    if len(wins) > 0 and len(losses) > 0:
        pf = wins["r"].sum() / abs(losses["r"].sum())
        print(f"Profit factor:     {pf:.2f}")
    print(f"Max drawdown (R):  {dd:.2f}")
    exit_counts = df["reason"].value_counts().to_dict()
    print(f"Exit reasons:      {exit_counts}")
    print("\nTrade log:")
    cols = ["entry_time", "exit_time", "dir", "entry", "stop", "t1", "t2", "exit", "reason", "r"]
    with pd.option_context("display.max_rows", None, "display.width", 160):
        print(df[cols].to_string(index=False))


# ─────────────────────────────── plot mode ───────────────────────────────

def plot_profiles(bars, out_path, months=6, weeks=12):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, axes = plt.subplots(2, 1, figsize=(15, 11))
    _plot_panel(axes[0], bars, freq="MS", n_periods=months,
                title=f"Monthly Volume Profiles (last {months} months)")
    _plot_panel(axes[1], bars, freq="W-MON", n_periods=weeks,
                title=f"Weekly Volume Profiles (last {weeks} weeks)")
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%Y"))
        ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(out_path, dpi=130)
    print(f"Saved {out_path}")


def _plot_panel(ax, bars, freq, n_periods, title):
    import matplotlib.dates as mdates

    profiles = period_profiles(bars, freq)[-n_periods:]
    if not profiles:
        return
    cutoff = profiles[0].start
    sub = bars[bars.index >= cutoff]
    ax.plot(sub.index, sub["close"], color="#222", lw=0.8, zorder=3)
    ax.set_title(title)
    ax.set_ylabel("Price")

    for p in profiles:
        seg = bars[(bars.index >= p.start) & (bars.index <= p.end)]
        if seg.empty:
            continue
        res = build_profile(seg, bins=50)
        if res is None:
            continue
        _poc, _vah, _val, _tot, centers, vols = res
        max_v = vols.max()
        if max_v <= 0:
            continue
        span = mdates.date2num(p.end) - mdates.date2num(p.start)
        bar_h = centers[1] - centers[0] if len(centers) > 1 else 1
        widths = [span * 0.85 * (v / max_v) for v in vols]
        left = mdates.date2num(p.start)
        for c, w in zip(centers, widths):
            if w <= 0:
                continue
            ax.barh(c, w, left=left, height=bar_h,
                    color="#4a90e2", alpha=0.35, edgecolor="none", zorder=2)
        ax.hlines(p.poc, p.start, p.end, color="#2e7d32", lw=1.4, zorder=4)
        ax.hlines(p.vah, p.start, p.end, color="#1565c0", lw=1.0, ls="--", zorder=4)
        ax.hlines(p.val, p.start, p.end, color="#c62828", lw=1.0, ls="--", zorder=4)


# ─────────────────────────────── entrypoint ───────────────────────────────

def _client_and_bars(args):
    key = os.getenv("ALPACA_API_KEY_ID")
    sec = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not sec:
        sys.exit("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY env vars.")
    feed = DataFeed.SIP if args.feed == "sip" else DataFeed.IEX
    client = StockHistoricalDataClient(key, sec)
    bars = fetch_hourly(args.symbol, args.months, client, feed)
    print(f"Fetched {len(bars)} hourly bars for {args.symbol} "
          f"({bars.index[0].date()} – {bars.index[-1].date()}, feed={args.feed})")
    return bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="analyze",
                    choices=["analyze", "backtest", "plot"])
    ap.add_argument("--symbol", default="QQQ")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--feed", choices=["iex", "sip"], default="iex")
    ap.add_argument("--out", default="qqq_profiles.png", help="plot output path")
    ap.add_argument("--hold-days", type=int, default=28, help="backtest max hold")
    args = ap.parse_args()

    bars = _client_and_bars(args)

    if args.mode == "analyze":
        monthly = period_profiles(bars, "MS")
        weekly = period_profiles(bars, "W-MON")
        price = float(bars["close"].iloc[-1])
        print_plan(args.symbol, monthly, weekly, price)
    elif args.mode == "backtest":
        df = run_backtest(bars, max_hold_days=args.hold_days)
        print_backtest(df)
        csv_out = args.out.replace(".png", ".csv") if args.out.endswith(".png") else args.out
        if not df.empty:
            df.to_csv(csv_out, index=False)
            print(f"\nSaved trade log → {csv_out}")
    else:
        plot_profiles(bars, args.out)


if __name__ == "__main__":
    main()
