"""Runner: management-variant comparison.

World 1 (stocks):  S2 cup-and-handle breakout entries on momentum leaders
                   (Q1+Q2), daily bars 2013-2018, replayed under 6 variants.
World 2 (S/D):     supply & demand first-retest entries on forex majors+minors,
                   index futures and metals, 4H bars 2013-2026, same 6 variants.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")

from .analytics import compute_metrics, metrics_by_group
from .run_phase1 import metrics_row
from .sd_zones import prep_4h, find_sd_entries
from .stock_selection import load_stocks, momentum_ranks, quintile_lookup, detect_s2, COST_RT_FRAC
from .trade_mgmt import replay_all, VARIANTS
from .data import load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "trade_mgmt")
os.makedirs(REPORT_DIR, exist_ok=True)

FX_INDICES_METALS = [
    # forex majors + minors (all 28 in repo)
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCAD", "AUDCHF", "AUDNZD",
    "NZDJPY", "NZDCAD", "NZDCHF", "CADJPY", "CADCHF", "CHFJPY",
    # indices
    "ES", "NQ", "YM", "RTY", "DAX", "NKD",
    # metals (no GC in repo)
    "SI", "HG", "PL", "PA",
]


def stocks_entries() -> tuple[dict, list[dict]]:
    """Collect S2 breakout entries on Q1+Q2 leaders. Returns (bars_by_ticker, entries)."""
    stocks = load_stocks()
    ranks = momentum_ranks(stocks)
    qlookup = quintile_lookup(ranks)
    entries = []
    for ticker, df in stocks.items():
        idx = df.index
        in_pos_until = -1
        for i in range(130, len(df)):
            if i <= in_pos_until:
                continue
            ts = idx[i]
            q = qlookup.get((ts.year, ts.month), {}).get(ticker)
            if q not in (1, 2):
                continue
            sig = detect_s2(df, i)
            if sig is None:
                continue
            entry = float(df.iloc[i]["close"]) * (1 + COST_RT_FRAC)
            if sig["stop"] >= entry:
                continue
            entries.append({
                "instrument": ticker, "ts": ts, "entry_i": i,
                "side": "long", "entry": entry, "stop": float(sig["stop"]),
            })
            in_pos_until = i + 15   # block overlapping re-entries (approx)
    return stocks, entries


def sd_entries_world() -> tuple[dict, list[dict]]:
    bars_by = {}
    entries = []
    have = {m["name"] for m in load_manifest()}
    for name in FX_INDICES_METALS:
        if name not in have:
            continue
        df = prep_4h(name)
        bars_by[name] = df
        found = find_sd_entries(name, df)
        # block overlapping entries (one position per instrument)
        found.sort(key=lambda e: e["entry_i"])
        pruned = []
        busy_until = -1
        for e in found:
            if e["entry_i"] <= busy_until:
                continue
            pruned.append(e)
            # violated fills are stopped the same bar -> position free again
            busy_until = e["entry_i"] + (0 if e["violated"] else 60)
        entries.extend(pruned)
        n_vio = sum(1 for e in pruned if e["violated"])
        print(f"  {name}: {len(pruned)} S/D fills ({n_vio} same-bar stopouts)")
    return bars_by, entries


def summarize(df: pd.DataFrame, label: str, split_ts: pd.Timestamp | None) -> dict:
    out = {}
    for v in VARIANTS:
        sub = df[df["variant"] == v].copy()
        if sub.empty:
            continue
        sub["pnl_pct"] = sub["r"] * 0.005
        sub["entry_ts"] = pd.to_datetime(sub["entry_ts"], utc=True)
        sub["exit_ts"] = sub["entry_ts"]  # approximation for equity ordering
        sub["bars"] = sub["bars_held"]
        sub = sub.sort_values("entry_ts")
        m_all = compute_metrics(sub)
        row = {"all": metrics_row(m_all)}
        if split_ts is not None:
            ins = sub[sub["entry_ts"] < split_ts]
            oos = sub[sub["entry_ts"] >= split_ts]
            if len(ins) >= 20:
                row["IS"] = metrics_row(compute_metrics(ins))
            if len(oos) >= 20:
                row["OOS"] = metrics_row(compute_metrics(oos))
        out[v] = row
        print(f"  {label} {v}: n={m_all.n_trades} pf={m_all.profit_factor:.2f} "
              f"avgR={m_all.avg_r:.3f} sumR={m_all.sum_r:.1f} dd_r={m_all.max_dd_r:.1f}")
    return out


def main():
    results = {}

    print("=== World 1: stocks breakout (S2 x Q1+Q2 leaders) ===")
    stocks, s_entries = stocks_entries()
    print(f"{len(s_entries)} breakout entries")
    rows = []
    for ticker, grp in pd.DataFrame(s_entries).groupby("instrument"):
        bars = stocks[ticker]
        rows.append(replay_all(bars, grp.to_dict(orient="records"), time_stop_bars=10))
    stock_replay = pd.concat(rows, ignore_index=True)
    stock_replay.to_csv(os.path.join(REPORT_DIR, "stocks_replay.csv"), index=False)
    results["stocks_S2_leaders"] = summarize(stock_replay, "STK", None)

    print("\n=== World 2: S/D forex+indices+metals ===")
    bars_by, f_entries = sd_entries_world()
    n_vio = sum(1 for e in f_entries if e["violated"])
    print(f"{len(f_entries)} S/D fills total ({n_vio} = "
          f"{100 * n_vio / max(len(f_entries), 1):.1f}% same-bar stopouts)")
    clean = [e for e in f_entries if not e["violated"]]
    violated = [e for e in f_entries if e["violated"]]
    rows = []
    for name, grp in pd.DataFrame(clean).groupby("instrument"):
        rows.append(replay_all(bars_by[name], grp.to_dict(orient="records"),
                               time_stop_bars=60))
    # violated fills are an immediate -1R under every variant
    vio_rows = [
        {"instrument": e["instrument"], "variant": v, "side": e["side"],
         "entry_ts": e["ts"], "r": -1.0, "bars_held": 0, "reason": "SAME_BAR_SL"}
        for e in violated for v in VARIANTS
    ]
    rows.append(pd.DataFrame(vio_rows))
    sd_replay = pd.concat(rows, ignore_index=True)
    sd_replay.to_csv(os.path.join(REPORT_DIR, "sd_replay.csv"), index=False)
    split = pd.Timestamp("2021-01-01", tz="UTC")
    results["sd_fx_indices_metals"] = summarize(sd_replay, "S/D", split)

    # per-asset-class breakdown for the S/D world (best variant determined later)
    sd_replay["entry_ts"] = pd.to_datetime(sd_replay["entry_ts"], utc=True)
    fx = set(n for n in FX_INDICES_METALS if len(n) == 6)
    idxs = {"ES", "NQ", "YM", "RTY", "DAX", "NKD"}
    def klass(x):
        if x in idxs:
            return "indices"
        if x in fx:
            return "forex"
        return "metals"
    sd_replay["klass"] = sd_replay["instrument"].map(klass)
    by_klass = {}
    for v in VARIANTS:
        sub = sd_replay[sd_replay["variant"] == v].copy()
        sub["pnl_pct"] = sub["r"] * 0.005
        sub["exit_ts"] = sub["entry_ts"]
        sub["bars"] = sub["bars_held"]
        by_klass[v] = {
            k: metrics_row(compute_metrics(g.sort_values("entry_ts")))
            for k, g in sub.groupby("klass")
        }
    results["sd_by_class"] = by_klass

    with open(os.path.join(REPORT_DIR, "trade_mgmt_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved trade_mgmt_results.json")


if __name__ == "__main__":
    main()
