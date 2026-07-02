"""Runner: stock-selection A/B/C test (leaders vs middle vs laggards)."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")

from .analytics import compute_metrics, monte_carlo, metrics_by_group
from .run_phase1 import plot_equity_and_dd, metrics_row
from .stock_selection import load_stocks, momentum_ranks, quintile_lookup, run_stock, es_regime

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "stock_selection")
os.makedirs(REPORT_DIR, exist_ok=True)

GROUPS = {
    "Q1_leaders": {1},
    "Q3_middle": {3},
    "Q5_laggards": {5},
}


def main():
    print("Loading stocks...")
    stocks = load_stocks()
    print(f"{len(stocks)} tickers eligible")

    print("Computing momentum ranks...")
    ranks = momentum_ranks(stocks)
    qlookup = quintile_lookup(ranks)
    print(f"{len(ranks)} rank rows over {ranks['month'].nunique()} months")

    regime = es_regime()

    results = {}
    all_dfs = {}
    for gname, quints in GROUPS.items():
        rows = []
        for ticker, df in stocks.items():
            rows.extend(run_stock(ticker, df, regime, qlookup, quints))
        gdf = pd.DataFrame(rows)
        if not gdf.empty:
            gdf = gdf.sort_values("entry_ts").reset_index(drop=True)
        all_dfs[gname] = gdf
        m = compute_metrics(gdf)
        results[gname] = metrics_row(m)
        print(f"{gname}: n={m.n_trades} wr={m.win_rate:.1%} pf={m.profit_factor:.2f} "
              f"avgR={m.avg_r:.3f} sumR={m.sum_r:.1f}")
        gdf.to_csv(os.path.join(REPORT_DIR, f"{gname}_trades.csv"), index=False)
        plot_equity_and_dd(gdf, gname, os.path.join(REPORT_DIR, f"{gname}_equity.png"))
        if len(gdf) >= 50:
            results[gname + "_monte_carlo"] = monte_carlo(gdf["r"].values, n_runs=1000)

    # breakdowns
    for gname, gdf in all_dfs.items():
        if gdf.empty:
            continue
        gdf["year"] = gdf["entry_ts"].dt.year
        results[gname + "_by_model"] = metrics_by_group(gdf, "model").to_dict(orient="records")
        results[gname + "_by_year"] = metrics_by_group(gdf, "year").to_dict(orient="records")

    with open(os.path.join(REPORT_DIR, "stock_selection_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Saved stock_selection_results.json")


if __name__ == "__main__":
    main()
