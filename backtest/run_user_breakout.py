"""User breakout playbook test: high-breakouts (non-extended) + MA-touch
reclaims via buy-stop over the indecisive candle, with sector-strength filter.

Objectified rules (from the user's description, declared before running):

B1  HIGH-BREAKOUT
    - Trigger: price crosses above the prior 20-day high (buy-stop resting
      at that level + 0.05 ATR since the prior close).
    - Extension filter (tested on/off): (stop_level - SMA50) / ATR14 < 4.
    - SL: min(low of last 10 bars before trigger) - 0.5 ATR, risk cap 12%.

B2  MA-TOUCH RECLAIM (50 or 200 SMA)
    - Context: uptrend (SMA50 rising over 20 bars for the 50-touch;
      close > SMA50 for the 200-touch).
    - Touch bar: low <= MA <= high on the touch bar.
    - Indecisive candle: |close-open| <= 0.4 x (high-low) on the touch bar.
    - Buy-stop at touch-bar high + 0.05 ATR, valid 5 bars.
    - Cancel if a bar's low breaks the touch-bar low before the stop fills.
      Trigger bar that also breaks the candle low -> conservative -1R.
    - SL variants: exact candle low (user rule) vs candle low - 0.25 ATR.

COMMON
    - TP fixed 2R vs 3R, set-and-forget. One position per ticker.
    - Costs 10 bps round trip baked into entry; stop fills at trigger+friction.
    - Sector filter (tested none / top5): GICS sector equal-weight return,
      blended rank of 21/63/126-day returns, computed on data up to the prior
      day; stock tradeable only if its sector ranks in the top 5 of 11.

Data: S&P 500 daily 2013-2018 (with volume); sector map = current GICS
(survivorship + sector-drift caveat documented in report).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .stock_selection import load_stocks, COST_RT_FRAC

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "user_breakout")
os.makedirs(REPORT_DIR, exist_ok=True)
SCRATCH = "/tmp/claude-0/-home-user-backtest-lab/c7ac16ab-376e-5108-8bd3-d7f3eb3fcfaf/scratchpad"


# ─────────────────────────────────────────────────────────────────────
# Sector strength (point-in-time from returns, static GICS map)
# ─────────────────────────────────────────────────────────────────────
def sector_map() -> dict[str, str]:
    comp = pd.read_csv(os.path.join(SCRATCH, "sp500_companies.csv"))
    return dict(zip(comp["Symbol"], comp["GICS Sector"]))


def sector_rank_table(stocks: dict, smap: dict) -> pd.DataFrame:
    """Daily blended sector rank. Row = date, col = sector, value = rank (1=best)."""
    closes = pd.DataFrame({t: df["close"] for t, df in stocks.items()})
    closes = closes.resample("1D").last().dropna(how="all")   # business days only
    sectors = sorted({smap.get(t) for t in closes.columns if smap.get(t)})
    sec_ret = {}
    for sec in sectors:
        members = [t for t in closes.columns if smap.get(t) == sec]
        if len(members) < 5:
            continue
        px = closes[members]
        # equal-weight blended momentum: mean of 21/63/126-day returns
        r21 = (px / px.shift(21) - 1).mean(axis=1)
        r63 = (px / px.shift(63) - 1).mean(axis=1)
        r126 = (px / px.shift(126) - 1).mean(axis=1)
        sec_ret[sec] = (r21.rank(pct=True) + r63.rank(pct=True) + r126.rank(pct=True))
    blend = pd.DataFrame(sec_ret)
    # cross-sectional rank per day (1 = strongest sector)
    return blend.rank(axis=1, ascending=False)


# ─────────────────────────────────────────────────────────────────────
# Setup detection & simulation
# ─────────────────────────────────────────────────────────────────────
def simulate_fixed(df, entry_i, entry, stop, tp_mult, max_bars=400):
    risk = entry - stop
    tp = entry + tp_mult * risk
    lows = df["low"].to_numpy()
    highs = df["high"].to_numpy()
    closes = df["close"].to_numpy()
    end_i = min(len(df) - 1, entry_i + max_bars)
    for j in range(entry_i + 1, end_i + 1):
        if lows[j] <= stop:
            return -1.0, j - entry_i, "SL"
        if highs[j] >= tp:
            return tp_mult, j - entry_i, "TP"
    return (closes[end_i] - entry) / risk, end_i - entry_i, "EOS"


def run_setup(stocks, sec_ranks, smap, setup: str, tp_mult: float,
              use_sector: bool, ext_filter: bool = True,
              sl_buffer: float = 0.0, top_n: int = 5) -> pd.DataFrame:
    recs = []
    # fast point-in-time sector lookup: shift(1) = prior-day rank, ffill,
    # then binary search on int64 timestamps.
    # IMPORTANT: force nanosecond units. pandas 3.0 indexes may be datetime64[us];
    # Timestamp.value is always ns — a unit mismatch here silently returned the
    # LAST row for every lookup (lookahead bug, caught 2026-07-02).
    sr = sec_ranks.shift(1).ffill()
    sr_ts = sr.index.as_unit("ns").asi8 if hasattr(sr.index, "as_unit") else sr.index.asi8
    sr_cols = {c: sr[c].to_numpy() for c in sr.columns}
    for ticker, df in stocks.items():
        sec = smap.get(ticker)
        if use_sector and sec not in sec_ranks.columns:
            continue
        closes = df["close"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        opens = df["open"].to_numpy()
        sma50 = df["sma50"].to_numpy()
        slope = df["sma50_slope"].to_numpy()
        atr = df["atr14"].to_numpy()
        sma200 = df["close"].rolling(200).mean().to_numpy() if setup == "B2_200" else None
        idx = df.index
        n = len(df)
        i = 210 if setup == "B2_200" else 80
        while i < n - 2:
            if np.isnan(atr[i]) or np.isnan(sma50[i]) or atr[i] <= 0:
                i += 1
                continue
            # sector gate at signal time (prior-day rank via shifted table)
            if use_sector:
                pos = np.searchsorted(sr_ts, idx[i].value, side="right") - 1
                rk = sr_cols[sec][pos] if pos >= 0 else np.nan
                if not np.isfinite(rk) or rk > top_n:
                    i += 1
                    continue

            filled = None
            if setup == "B1":
                hh20 = highs[i - 20:i].max()
                trigger = hh20 + 0.05 * atr[i]
                if ext_filter and (trigger - sma50[i]) / atr[i] >= 4:
                    i += 1
                    continue
                # stop order rests; look for fill in next 5 bars
                for B in range(i + 1, min(i + 6, n)):
                    if highs[B] >= trigger:
                        entry = trigger * (1 + COST_RT_FRAC)
                        stop = lows[max(0, B - 10):B].min() - 0.5 * atr[i]
                        filled = (B, entry, stop)
                        break
                    if closes[B] < sma50[B]:
                        break
            else:  # B2_50 / B2_200
                ma = sma50 if setup == "B2_50" else sma200
                if setup == "B2_50" and slope[i] <= 0:
                    i += 1
                    continue
                if setup == "B2_200" and (np.isnan(ma[i]) or closes[i] < sma50[i] * 0.97):
                    i += 1
                    continue
                touched = lows[i] <= ma[i] <= highs[i]
                rng = highs[i] - lows[i]
                indecisive = rng > 0 and abs(closes[i] - opens[i]) <= 0.4 * rng
                if not (touched and indecisive):
                    i += 1
                    continue
                trigger = highs[i] + 0.05 * atr[i]
                cancel_lvl = lows[i]
                for B in range(i + 1, min(i + 6, n)):
                    hit_stop_first = lows[B] <= cancel_lvl
                    triggered = highs[B] >= trigger
                    if triggered:
                        entry = trigger * (1 + COST_RT_FRAC)
                        stop = lows[i] - sl_buffer * atr[i]
                        if hit_stop_first:
                            # conservative: filled then stopped same bar
                            recs.append({"ticker": ticker, "ts": idx[B], "r": -1.0,
                                         "bars": 0, "reason": "SAME_BAR_SL"})
                            i = B + 1
                            filled = "done"
                        else:
                            filled = (B, entry, stop)
                        break
                    if hit_stop_first:
                        break   # cancelled before trigger

            if filled == "done":
                continue
            if filled is None:
                i += 1
                continue
            B, entry, stop = filled
            if stop >= entry or (entry - stop) / entry > 0.12:
                i = B + 1
                continue
            r, bars, reason = simulate_fixed(df, B, entry, stop, tp_mult)
            recs.append({"ticker": ticker, "ts": idx[B], "r": r,
                         "bars": bars, "reason": reason})
            i = B + max(bars, 1)

    return pd.DataFrame(recs)


def summarize(tdf: pd.DataFrame) -> dict:
    if tdf.empty:
        return {"n": 0}
    r = tdf["r"].to_numpy()
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    return {
        "n": int(len(r)),
        "win_rate": round(float(wins.mean()), 3),
        "avg_r": round(float(r.mean()), 3),
        "pf": round(float(pos / neg), 2) if neg > 0 else None,
        "sum_r": round(float(r.sum()), 1),
        "avg_hold_d": round(float(tdf["bars"].mean()), 1),
    }


def main():
    stocks = load_stocks()
    smap = sector_map()
    print("Building sector ranks...")
    sec_ranks = sector_rank_table(stocks, smap)
    covered = sum(1 for t in stocks if smap.get(t) in sec_ranks.columns)
    print(f"{covered}/{len(stocks)} tickers with sector mapping")

    results = {}
    grid = []
    # B1: ext on/off x TP 2/3 x sector none/top5
    for ext in (True, False):
        for tp in (2.0, 3.0):
            for sec in (False, True):
                key = f"B1|ext{'ON' if ext else 'OFF'}|TP{int(tp)}R|sec{'TOP5' if sec else 'ALL'}"
                tdf = run_setup(stocks, sec_ranks, smap, "B1", tp, sec, ext_filter=ext)
                m = summarize(tdf)
                m["cell"] = key
                grid.append(m)
                print(f"{key:34s} n={m.get('n')} wr={m.get('win_rate')} "
                      f"pf={m.get('pf')} avgR={m.get('avg_r')}")
    # B2: setup 50/200 x SL exact/buffer x TP 2/3, sector top5 fixed after B1 verdict? -> test both sector modes at TP3
    for setup in ("B2_50", "B2_200"):
        for slb in (0.0, 0.25):
            for tp in (2.0, 3.0):
                for sec in (False, True):
                    key = (f"{setup}|SL{'exact' if slb == 0 else 'buf.25'}|"
                           f"TP{int(tp)}R|sec{'TOP5' if sec else 'ALL'}")
                    tdf = run_setup(stocks, sec_ranks, smap, setup, tp, sec,
                                    sl_buffer=slb)
                    m = summarize(tdf)
                    m["cell"] = key
                    grid.append(m)
                    print(f"{key:34s} n={m.get('n')} wr={m.get('win_rate')} "
                          f"pf={m.get('pf')} avgR={m.get('avg_r')}")

    results["grid"] = grid
    pd.DataFrame(grid).to_csv(os.path.join(REPORT_DIR, "user_breakout_grid.csv"),
                              index=False)
    with open(os.path.join(REPORT_DIR, "user_breakout_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved user_breakout_results.json")


if __name__ == "__main__":
    main()
