"""SMA vs EMA for reversal signals — two focused paired tests.

Test A (pullback reversal in uptrend, stocks 2013-2018):
  S3-style entry on momentum leaders (Q1+Q2): price tags the MA, closes back
  above it, uptrend filter (close > SMA50, >=15 of last 20 closes above MA20-
  type). Stop = pullback low - 0.5 ATR, TP fixed 2R, set-and-forget.
  Variants: {EMA, SMA} x {10, 20} as the tagged MA. Same stocks, same rules.

Test B (trend-reversal cross, index futures daily 2013-2026):
  Long-only: enter on close crossing above MA, exit on close crossing below.
  Variants: {EMA, SMA} x {10, 20, 50, 100, 200}. Costs per round trip applied.
  Metric: n trades, win rate, avg trade %, profit factor, total return %.

Both tests share data and costs across variants -> differences attributable
to MA type/length alone.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest
from .mp1 import daily_bars
from .stock_selection import load_stocks, momentum_ranks, quintile_lookup, COST_RT_FRAC

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "ma_compare")
os.makedirs(REPORT_DIR, exist_ok=True)

INDEX_UNIVERSE = ["NQ", "ES", "YM", "RTY", "DAX", "NKD"]


def ma(series: pd.Series, kind: str, n: int) -> pd.Series:
    if kind == "SMA":
        return series.rolling(n).mean()
    return series.ewm(span=n, adjust=False).mean()


# ─────────────────────────────────────────────────────────────────────
# Test A — pullback-tag reversal (stocks, leaders)
# ─────────────────────────────────────────────────────────────────────
def test_a():
    stocks = load_stocks()
    ranks = momentum_ranks(stocks)
    qlookup = quintile_lookup(ranks)

    variants = [("EMA", 10), ("SMA", 10), ("EMA", 20), ("SMA", 20)]
    results = {}
    for kind, n in variants:
        recs = []
        for ticker, df in stocks.items():
            c = df["close"]
            m = ma(c, kind, n).to_numpy()
            sma50 = df["sma50"].to_numpy()
            atr = df["atr14"].to_numpy()
            highs = df["high"].to_numpy()
            lows = df["low"].to_numpy()
            closes = c.to_numpy()
            vol = df["volume"].to_numpy()
            vavg = df["vol_avg20"].to_numpy()
            idx = df.index
            i = 130
            while i < len(df) - 1:
                ts = idx[i]
                q = qlookup.get((ts.year, ts.month), {}).get(ticker)
                if q not in (1, 2):
                    i += 1
                    continue
                if np.isnan(m[i]) or np.isnan(sma50[i]) or np.isnan(atr[i]):
                    i += 1
                    continue
                # uptrend filter
                if closes[i] < sma50[i]:
                    i += 1
                    continue
                above = sum(closes[j] > m[j] for j in range(i - 20, i)
                            if not np.isnan(m[j]))
                if above < 15:
                    i += 1
                    continue
                # tag + reclaim + non-distribution volume
                tol = 0.3 * atr[i]
                tagged = lows[i] <= m[i] + tol
                reclaim = closes[i] >= m[i]
                if not (tagged and reclaim) or np.isnan(vavg[i]) or vol[i] > vavg[i]:
                    i += 1
                    continue
                entry = closes[i] * (1 + COST_RT_FRAC)
                stop = min(lows[i], lows[i - 1]) - 0.5 * atr[i]
                risk = entry - stop
                if risk <= 0:
                    i += 1
                    continue
                tp = entry + 2 * risk
                # simulate set-and-forget
                r_out, bars_held = None, 0
                for j in range(i + 1, min(len(df), i + 401)):
                    bars_held = j - i
                    if lows[j] <= stop:
                        r_out = -1.0
                        break
                    if highs[j] >= tp:
                        r_out = 2.0
                        break
                if r_out is None:
                    j = min(len(df) - 1, i + 400)
                    r_out = (closes[j] - entry) / risk
                recs.append({"r": r_out, "ts": ts})
                i += max(bars_held, 1)   # one position per ticker
        rr = np.array([x["r"] for x in recs])
        wins = rr > 0
        pf = rr[wins].sum() / abs(rr[~wins].sum()) if (~wins).any() else float("inf")
        results[f"{kind}{n}"] = {
            "n": int(len(rr)), "win_rate": round(float(wins.mean()), 3),
            "avg_r": round(float(rr.mean()), 4), "pf": round(float(pf), 3),
            "sum_r": round(float(rr.sum()), 1),
        }
        print(f"A {kind}{n}: n={len(rr)} wr={wins.mean():.2%} pf={pf:.2f} avgR={rr.mean():+.3f}")
    return results


# ─────────────────────────────────────────────────────────────────────
# Test B — trend-reversal cross (indices daily)
# ─────────────────────────────────────────────────────────────────────
def test_b():
    metas = {m["name"]: m for m in load_manifest()}
    variants = [(k, n) for k in ("EMA", "SMA") for n in (10, 20, 50, 100, 200)]
    results = {}
    data = {}
    for name in INDEX_UNIVERSE:
        df = daily_bars(name)
        cost = cost_for(name, metas[name].get("jpy", False), metas[name]["type"],
                        metas[name]["category"], metas[name].get("tick"))
        fr = (cost.spread_price + cost.slippage_price)
        data[name] = (df, fr)

    for kind, n in variants:
        trades = []
        for name, (df, fr) in data.items():
            c = df["close"]
            m = ma(c, kind, n).to_numpy()
            closes = c.to_numpy()
            in_pos = False
            entry = 0.0
            for i in range(max(n + 1, 2), len(df)):
                if np.isnan(m[i]) or np.isnan(m[i - 1]):
                    continue
                above = closes[i] > m[i]
                above_prev = closes[i - 1] > m[i - 1]
                if not in_pos and above and not above_prev:
                    entry = closes[i] + fr
                    in_pos = True
                elif in_pos and not above and above_prev:
                    trades.append((closes[i] - fr) / entry - 1)
                    in_pos = False
            if in_pos:
                trades.append((closes[-1] - fr) / entry - 1)
        tr = np.array(trades)
        wins = tr > 0
        pf = tr[wins].sum() / abs(tr[~wins].sum()) if (~wins).any() else float("inf")
        results[f"{kind}{n}"] = {
            "n": int(len(tr)), "win_rate": round(float(wins.mean()), 3),
            "avg_trade_pct": round(float(tr.mean() * 100), 3),
            "pf": round(float(pf), 3),
            "sum_return_pct": round(float(tr.sum() * 100), 1),
        }
        print(f"B {kind}{n}: n={len(tr)} wr={wins.mean():.2%} pf={pf:.2f} "
              f"avgTrade={tr.mean() * 100:+.3f}%")
    return results


def main():
    print("=== Test A: pullback-tag reversal (stocks, Q1+Q2 leaders) ===")
    a = test_a()
    print("\n=== Test B: MA-cross trend reversal (index futures daily) ===")
    b = test_b()
    with open(os.path.join(REPORT_DIR, "ma_compare_results.json"), "w") as f:
        json.dump({"test_a_pullback": a, "test_b_cross": b}, f, indent=2)
    print("\nSaved ma_compare_results.json")


if __name__ == "__main__":
    main()
