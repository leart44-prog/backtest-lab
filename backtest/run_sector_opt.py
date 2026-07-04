"""Sector-selection optimization on the B1 high-breakout setup.

Fixed: B1, extension filter ON, TP 3R, SL 10-bar-low - 0.5 ATR (the v2.1
primary setup). Varied (declared a priori, all cells reported):

  Lookback for sector momentum: 21d / 63d / 126d / blend(21+63+126)
  Strictness: top 3 / top 5 / top 8 of 11 sectors
  Mode: absolute rank vs relative strength (sector return > market return,
        market = equal-weight all mapped stocks)

Plus: monthly turnover of the top-N set (tradability) and per-year
consistency for the recommended cell vs the v2.1 default (blend/top5).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .run_user_breakout import run_setup, sector_map, SCRATCH
from .stock_selection import load_stocks

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "sector_opt")
os.makedirs(REPORT_DIR, exist_ok=True)


def build_rank_table(stocks, smap, lookbacks: list[int]) -> pd.DataFrame:
    closes = pd.DataFrame({t: df["close"] for t, df in stocks.items()})
    closes = closes.resample("1D").last().dropna(how="all")
    sectors = sorted({smap.get(t) for t in closes.columns if smap.get(t)})
    blend = {}
    for sec in sectors:
        members = [t for t in closes.columns if smap.get(t) == sec]
        if len(members) < 5:
            continue
        px = closes[members]
        score = None
        for lb in lookbacks:
            r = (px / px.shift(lb) - 1).mean(axis=1).rank(pct=True)
            score = r if score is None else score + r
        blend[sec] = score
    df = pd.DataFrame(blend)
    return df.rank(axis=1, ascending=False)


def build_rs_table(stocks, smap, lookbacks: list[int]) -> pd.DataFrame:
    """Relative strength: rank 1 if sector return beats market on the blend,
    else 99. Produces variable breadth (0..11 sectors allowed)."""
    closes = pd.DataFrame({t: df["close"] for t, df in stocks.items()})
    closes = closes.resample("1D").last().dropna(how="all")
    mapped = [t for t in closes.columns if smap.get(t)]
    market = closes[mapped]
    sectors = sorted({smap.get(t) for t in mapped})
    out = {}
    for sec in sectors:
        members = [t for t in closes.columns if smap.get(t) == sec]
        if len(members) < 5:
            continue
        px = closes[members]
        beats = None
        for lb in lookbacks:
            sec_r = (px / px.shift(lb) - 1).mean(axis=1)
            mkt_r = (market / market.shift(lb) - 1).mean(axis=1)
            b = sec_r > mkt_r
            beats = b if beats is None else (beats & b)
        out[sec] = np.where(beats, 1.0, 99.0)
    return pd.DataFrame(out, index=closes.index)


def cell_stats(tdf: pd.DataFrame) -> dict:
    if tdf.empty:
        return {"n": 0}
    r = tdf["r"].to_numpy()
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    return {
        "n": int(len(r)), "win_rate": round(float(wins.mean()), 3),
        "avg_r": round(float(r.mean()), 3),
        "pf": round(float(pos / neg), 2) if neg > 0 else None,
        "sum_r": round(float(r.sum()), 1),
    }


def turnover(rank_tbl: pd.DataFrame, top_n: int) -> float:
    """Average monthly change count of the top-N sector set."""
    monthly = rank_tbl.resample("ME").last().dropna(how="all")
    sets = [frozenset(row[row <= top_n].index) for _, row in monthly.iterrows()]
    changes = [len(a.symmetric_difference(b)) / 2 for a, b in zip(sets, sets[1:])]
    return round(float(np.mean(changes)), 2) if changes else 0.0


def main():
    stocks = load_stocks()
    smap = sector_map()

    LOOKBACKS = {"1M": [21], "3M": [63], "6M": [126], "blend": [21, 63, 126]}
    grid = []

    for lb_name, lbs in LOOKBACKS.items():
        tbl = build_rank_table(stocks, smap, lbs)
        for top_n in (3, 5, 8):
            tdf = run_setup(stocks, tbl, smap, "B1", 3.0, True,
                            ext_filter=True, top_n=top_n)
            m = cell_stats(tdf)
            m["cell"] = f"rank|{lb_name}|top{top_n}"
            m["monthly_turnover"] = turnover(tbl, top_n)
            grid.append(m)
            print(f"rank|{lb_name}|top{top_n}: n={m['n']} pf={m['pf']} "
                  f"avgR={m['avg_r']} turnover={m['monthly_turnover']}")

    # relative-strength mode (must beat market on every lookback in set)
    for lb_name, lbs in (("3M", [63]), ("blend", [21, 63, 126])):
        tbl = build_rs_table(stocks, smap, lbs)
        tdf = run_setup(stocks, tbl, smap, "B1", 3.0, True,
                        ext_filter=True, top_n=1)   # rank 1 = beats market
        m = cell_stats(tdf)
        m["cell"] = f"RS>{lb_name}|market"
        m["monthly_turnover"] = turnover(tbl, 1)
        grid.append(m)
        print(f"RS>{lb_name}: n={m['n']} pf={m['pf']} avgR={m['avg_r']}")

    # baseline: no sector filter
    tbl0 = build_rank_table(stocks, smap, [21, 63, 126])
    tdf = run_setup(stocks, tbl0, smap, "B1", 3.0, False, ext_filter=True)
    m = cell_stats(tdf)
    m["cell"] = "no_sector_filter"
    grid.append(m)
    print(f"no filter: n={m['n']} pf={m['pf']} avgR={m['avg_r']}")

    # per-year for candidate cells
    yearly = {}
    for label, lbs, tn in (("blend_top5", [21, 63, 126], 5),
                           ("3M_top3", [63], 3),
                           ("6M_top3", [126], 3)):
        tbl = build_rank_table(stocks, smap, lbs)
        tdf = run_setup(stocks, tbl, smap, "B1", 3.0, True,
                        ext_filter=True, top_n=tn)
        tdf["year"] = pd.to_datetime(tdf["ts"]).dt.year
        yearly[label] = {int(y): cell_stats(g) for y, g in tdf.groupby("year")}
        print(f"\n{label} by year:")
        for y, s in yearly[label].items():
            print(f"  {y}: n={s['n']} pf={s['pf']} avgR={s['avg_r']}")

    out = {"grid": grid, "yearly": yearly}
    pd.DataFrame(grid).to_csv(os.path.join(REPORT_DIR, "sector_opt_grid.csv"),
                              index=False)
    with open(os.path.join(REPORT_DIR, "sector_opt_results.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("\nSaved sector_opt_results.json")


if __name__ == "__main__":
    main()
