"""Breakout strategy (S2 cup-and-handle on momentum leaders): TP/SL grid +
VIX-scaled position sizing.

A-priori declarations (before looking at results):
  - Entries: S2 breakout, Q1+Q2 momentum quintiles, unchanged from the
    trade-management study (n~400, 2013-2018). Entry at breakout close,
    10 bps round-trip cost baked into entry.
  - SL grid:   HL-0.5A (handle low - 0.5 ATR, baseline), HL (structural),
               E-1.0A (entry - 1.0 ATR, tight), E-1.5A (entry - 1.5 ATR)
  - TP grid:   2R / 3R (baseline) / 4R, set-and-forget
               plus one management check: 3R with 50% partial at 1R + BE
  - Baseline cell: SL=HL-0.5A, TP=3R (winner of the management study).
  - Sizing models (VIX close of the last day BEFORE entry, no lookahead):
      Z1 fixed 0.5%
      Z2 inverse:  0.5% x (17 / VIX_prev), clamped to [0.25%, 1.0%]
      Z3 tiered:   VIX<15 -> 0.75% | 15-25 -> 0.5% | >25 -> 0.25%
  - All 13 grid cells are reported; no cell is dropped.

Conservative intrabar rule: stop before target. Same-bar-BE rule applied in
the partial variant (post-audit engine).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "breakout_opt")
os.makedirs(REPORT_DIR, exist_ok=True)

SCRATCH = "/tmp/claude-0/-home-user-backtest-lab/c7ac16ab-376e-5108-8bd3-d7f3eb3fcfaf/scratchpad"

SL_MODES = ("HL-0.5A", "HL", "E-1.0A", "E-1.5A")
TP_MODES = ("2R", "3R", "4R")


def collect_entries():
    from .run_trade_mgmt import stocks_entries
    from .stock_selection import load_stocks
    stocks, entries = stocks_entries()
    # enrich with atr at entry for SL variants
    out = []
    for e in entries:
        df = stocks[e["instrument"]]
        i = e["entry_i"]
        atr = float(df.iloc[i]["atr14"])
        if np.isnan(atr) or atr <= 0:
            continue
        e2 = dict(e)
        e2["atr"] = atr
        e2["handle_stop_base"] = e["stop"]           # handle_low - 0.5*ATR (from detect_s2)
        e2["handle_low"] = e["stop"] + 0.5 * atr     # reconstruct raw handle low
        out.append(e2)
    return stocks, out


def sl_price(e: dict, mode: str) -> float:
    if mode == "HL-0.5A":
        return e["handle_low"] - 0.5 * e["atr"]
    if mode == "HL":
        return e["handle_low"]
    if mode == "E-1.0A":
        return e["entry"] - 1.0 * e["atr"]
    if mode == "E-1.5A":
        return e["entry"] - 1.5 * e["atr"]
    raise ValueError(mode)


def simulate(df: pd.DataFrame, entry_i: int, entry: float, stop: float,
             tp_mult: float, partial_1r: bool = False, max_bars: int = 400) -> dict:
    """Long set-and-forget with fixed TP; optional 50% partial at +1R + BE.
    Conservative: stop before target; freshly moved BE stop checked same bar."""
    risk = entry - stop
    if risk <= 0:
        return {"r": 0.0, "bars": 0, "reason": "BAD"}
    tp = entry + tp_mult * risk
    p_lvl = entry + risk
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    n = len(df)
    end_i = min(n - 1, entry_i + max_bars)
    frac, realized, partial_done = 1.0, 0.0, False

    for i in range(entry_i + 1, end_i + 1):
        lo, hi = lows[i], highs[i]
        held = i - entry_i
        if lo <= stop:
            realized += frac * (stop - entry) / risk
            return {"r": realized, "bars": held,
                    "reason": "SL" if not partial_done else "BE"}
        if partial_1r and not partial_done and hi >= p_lvl:
            realized += 0.5 * 1.0
            frac = 0.5
            stop = entry
            partial_done = True
            if lo <= stop:               # conservative same-bar BE check
                return {"r": realized, "bars": held, "reason": "BE_SAME_BAR"}
        if hi >= tp:
            realized += frac * (tp - entry) / risk
            return {"r": realized, "bars": held, "reason": "TP"}
    realized += frac * (closes[end_i] - entry) / risk
    return {"r": realized, "bars": end_i - entry_i, "reason": "EOS"}


def cell_metrics(trades: pd.DataFrame, risk_series: np.ndarray | None = None,
                 start_eq: float = 100_000.0) -> dict:
    r = trades["r"].to_numpy()
    n = len(r)
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    pf = pos / neg if neg > 0 else float("inf")
    risks = risk_series if risk_series is not None else np.full(n, 0.005)
    eq = start_eq
    peak, maxdd = eq, 0.0
    curve = []
    for rr, rk in zip(r, risks):
        eq *= (1 + rr * rk)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)
        curve.append(eq)
    years = (trades["entry_ts"].iloc[-1] - trades["entry_ts"].iloc[0]).days / 365.25
    cagr = (eq / start_eq) ** (1 / max(years, 0.5)) - 1
    pnl = r * risks
    sharpe = pnl.mean() / pnl.std() * np.sqrt(52) if pnl.std() > 0 else 0.0
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    return {
        "n": int(n), "win_rate": round(float(wins.mean()), 3),
        "avg_r": round(float(r.mean()), 3), "pf": round(float(pf), 2),
        "sum_r": round(float(r.sum()), 1),
        "max_dd_pct": round(100 * maxdd, 2),
        "cagr_pct": round(100 * cagr, 2),
        "final_equity": round(eq, 0),
        "ret_dd": round(float((eq / start_eq - 1) / max(maxdd, 1e-9)), 2),
        "sharpe": round(float(sharpe), 2),
        "max_loss_streak": int(best),
        "avg_hold_days": round(float(trades["bars"].mean()), 1),
    }


def main():
    stocks, entries = collect_entries()
    print(f"{len(entries)} breakout entries")

    vix = pd.read_csv(os.path.join(SCRATCH, "vix-daily.csv"), parse_dates=["DATE"])
    vix = vix.set_index("DATE")["CLOSE"].sort_index()

    def vix_before(ts) -> float:
        t = pd.Timestamp(ts).tz_localize(None).normalize()
        prior = vix.loc[:t - pd.Timedelta(days=1)]
        return float(prior.iloc[-1]) if len(prior) else 17.0

    # ── TP x SL grid, fixed 0.5% sizing ──
    grid_rows = []
    trades_by_cell = {}
    cells = [(sl, tp, False) for sl in SL_MODES for tp in TP_MODES]
    cells.append(("HL-0.5A", "3R", True))     # management check cell
    for sl_mode, tp_mode, partial in cells:
        recs = []
        tp_mult = float(tp_mode[0])
        for e in entries:
            stop = sl_price(e, sl_mode)
            if stop >= e["entry"]:
                continue
            res = simulate(stocks[e["instrument"]], e["entry_i"], e["entry"],
                           stop, tp_mult, partial_1r=partial)
            recs.append({"entry_ts": e["ts"], "r": res["r"], "bars": res["bars"],
                         "reason": res["reason"], "instrument": e["instrument"]})
        tdf = pd.DataFrame(recs).sort_values("entry_ts").reset_index(drop=True)
        key = f"{sl_mode}|{tp_mode}{'|partial' if partial else ''}"
        trades_by_cell[key] = tdf
        m = cell_metrics(tdf)
        m["cell"] = key
        grid_rows.append(m)
        print(f"{key:22s} n={m['n']} wr={m['win_rate']:.2f} pf={m['pf']:.2f} "
              f"avgR={m['avg_r']:+.3f} dd={m['max_dd_pct']:.1f}% cagr={m['cagr_pct']:.1f}%")

    grid_df = pd.DataFrame(grid_rows)
    grid_df.to_csv(os.path.join(REPORT_DIR, "grid_results.csv"), index=False)

    # ── VIX sizing on baseline cell + best cell by ret_dd ──
    baseline_key = "HL-0.5A|3R"
    best_key = grid_df.sort_values("ret_dd", ascending=False).iloc[0]["cell"]
    sizing_rows = []
    for key in dict.fromkeys([baseline_key, best_key]):
        tdf = trades_by_cell[key]
        vix_prev = np.array([vix_before(ts) for ts in tdf["entry_ts"]])
        sizings = {
            "Z1_fixed_0.5%": np.full(len(tdf), 0.005),
            "Z2_inverse_17/VIX": np.clip(0.005 * 17.0 / vix_prev, 0.0025, 0.010),
            "Z3_tiered": np.where(vix_prev < 15, 0.0075,
                                  np.where(vix_prev <= 25, 0.005, 0.0025)),
        }
        for zname, risks in sizings.items():
            m = cell_metrics(tdf, risk_series=risks)
            m["cell"] = key
            m["sizing"] = zname
            m["avg_risk_pct"] = round(float(risks.mean() * 100), 3)
            sizing_rows.append(m)
            print(f"{key} {zname}: cagr={m['cagr_pct']:.1f}% dd={m['max_dd_pct']:.1f}% "
                  f"ret/dd={m['ret_dd']:.2f} sharpe={m['sharpe']:.2f}")

    sizing_df = pd.DataFrame(sizing_rows)
    sizing_df.to_csv(os.path.join(REPORT_DIR, "sizing_results.csv"), index=False)

    with open(os.path.join(REPORT_DIR, "breakout_opt_results.json"), "w") as f:
        json.dump({"grid": grid_rows, "sizing": sizing_rows,
                   "baseline": baseline_key, "best_by_ret_dd": best_key},
                  f, indent=2, default=str)
    print("\nSaved breakout_opt_results.json")


if __name__ == "__main__":
    main()
