"""Sector framework component test — on top of the established 3M/top3 gate.

Candidate confirmations (tested one at a time on B1, TP3R, extON):
  BASE        rank63 top3 (v2.2 gate, reference)
  +BREADTH    additionally >= 60% of sector members above their 50-SMA
  +RSLINE     additionally sector EW index / SPY-proxy above its own 20d MA
  IMPROVING   rank21 <= 3 but rank63 > 3 (emerging leadership)
  LEADING     rank63 <= 3 and rank21 <= 3 (established leadership)
  IMP+LEAD    union
All point-in-time (prior-day data only).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .run_user_breakout import run_setup, sector_map
from .run_sector_opt import build_rank_table, cell_stats
from .stock_selection import load_stocks

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "sector_framework")
os.makedirs(REPORT_DIR, exist_ok=True)


def build_tables(stocks, smap):
    closes = pd.DataFrame({t: df["close"] for t, df in stocks.items()})
    closes = closes.resample("1D").last().dropna(how="all")
    mapped = [t for t in closes.columns if smap.get(t)]
    sectors = sorted({smap.get(t) for t in mapped})

    rank63 = build_rank_table(stocks, smap, [63])
    rank21 = build_rank_table(stocks, smap, [21])

    # breadth: % of members above their 50-SMA
    sma50 = closes.rolling(50, min_periods=40).mean()
    above = closes > sma50
    breadth = {}
    rsline_ok = {}
    spy_proxy = closes[mapped].mean(axis=1)   # EW market proxy
    for sec in sectors:
        members = [t for t in mapped if smap.get(t) == sec]
        if len(members) < 5:
            continue
        breadth[sec] = above[members].mean(axis=1)
        sec_idx = closes[members].mean(axis=1)
        ratio = sec_idx / spy_proxy
        rsline_ok[sec] = ratio > ratio.rolling(20, min_periods=15).mean()
    return rank63, rank21, pd.DataFrame(breadth), pd.DataFrame(rsline_ok)


def gate_table(rank63, rank21, breadth, rsline, mode: str) -> pd.DataFrame:
    """Return table where value 1 = sector allowed, 99 = blocked."""
    r63 = rank63.reindex(breadth.index).ffill()
    r21 = rank21.reindex(breadth.index).ffill()
    if mode == "BASE":
        ok = r63 <= 3
    elif mode == "BREADTH":
        ok = (r63 <= 3) & (breadth >= 0.60)
    elif mode == "RSLINE":
        ok = (r63 <= 3) & rsline.reindex(breadth.index).fillna(False)
    elif mode == "IMPROVING":
        ok = (r21 <= 3) & (r63 > 3)
    elif mode == "LEADING":
        ok = (r63 <= 3) & (r21 <= 3)
    elif mode == "IMP+LEAD":
        ok = (r21 <= 3) | (r63 <= 3)
    else:
        raise ValueError(mode)
    return ok.astype(float).replace({1.0: 1.0, 0.0: 99.0})


def main():
    stocks = load_stocks()
    smap = sector_map()
    rank63, rank21, breadth, rsline = build_tables(stocks, smap)

    grid = []
    yearly = {}
    for mode in ("BASE", "BREADTH", "RSLINE", "IMPROVING", "LEADING", "IMP+LEAD"):
        tbl = gate_table(rank63, rank21, breadth, rsline, mode)
        tdf = run_setup(stocks, tbl, smap, "B1", 3.0, True,
                        ext_filter=True, top_n=1)
        m = cell_stats(tdf)
        m["cell"] = mode
        grid.append(m)
        if not tdf.empty:
            tdf["year"] = pd.to_datetime(tdf["ts"]).dt.year
            yearly[mode] = {int(y): cell_stats(g) for y, g in tdf.groupby("year")}
        print(f"{mode:10s} n={m.get('n')} wr={m.get('win_rate')} "
              f"pf={m.get('pf')} avgR={m.get('avg_r')}")

    pd.DataFrame(grid).to_csv(os.path.join(REPORT_DIR, "framework_grid.csv"),
                              index=False)
    with open(os.path.join(REPORT_DIR, "framework_results.json"), "w") as f:
        json.dump({"grid": grid, "yearly": yearly}, f, indent=2)
    print("Saved framework_results.json")


if __name__ == "__main__":
    main()
