"""MP-1 Swing-Only runner: indices core + commodities robustness group."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")

from .analytics import compute_metrics, monte_carlo, metrics_by_group, split_in_out_sample
from .mp1 import (
    INDEX_UNIVERSE, ROBUSTNESS_UNIVERSE, REGIME_TICKER,
    daily_bars, add_indicators, regime_series, run_mp1_instrument,
)
from .run_phase1 import plot_equity_and_dd, plot_monte_carlo, metrics_row

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "mp1")
os.makedirs(REPORT_DIR, exist_ok=True)


def run_universe(names: list[str], regime: pd.Series, label: str,
                 own_regime: bool = False) -> pd.DataFrame:
    rows = []
    for name in names:
        df = add_indicators(daily_bars(name))
        reg = regime_series(df) if own_regime else regime
        trades = run_mp1_instrument(name, df, reg)
        rows.extend(trades)
        print(f"  {name}: {len(trades)} trades")
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("entry_ts").reset_index(drop=True)
    print(f"{label}: {len(out)} total")
    return out


def main():
    print("=== MP-1 Swing-Only ===")
    nq = add_indicators(daily_bars(REGIME_TICKER))
    regime = regime_series(nq)
    print(f"Regime distribution:\n{regime.value_counts()}")

    split_ts = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}

    print("\n-- Core: index futures (shared NQ regime) --")
    core = run_universe(INDEX_UNIVERSE, regime, "CORE")
    print("\n-- Robustness: commodities (own-instrument regime) --")
    robust = run_universe(ROBUSTNESS_UNIVERSE, regime, "ROBUST", own_regime=True)

    for label, df in (("MP1_indices", core), ("MP1_commodities", robust)):
        if df.empty:
            results[label] = {}
            continue
        ins, oos = split_in_out_sample(df, split_ts)
        results[label] = {
            "all": metrics_row(compute_metrics(df)),
            "in_sample_2013_2020": metrics_row(compute_metrics(ins)),
            "out_of_sample_2021_2026": metrics_row(compute_metrics(oos)),
        }
        df.to_csv(os.path.join(REPORT_DIR, f"{label}_trades.csv"), index=False)
        plot_equity_and_dd(df, label, os.path.join(REPORT_DIR, f"{label}_equity.png"))
        if len(df) >= 30:
            results[label + "_monte_carlo"] = monte_carlo(df["r"].values, n_runs=1000)
            plot_monte_carlo(df, label, os.path.join(REPORT_DIR, f"{label}_montecarlo.png"))

    # Breakdowns for core
    if not core.empty:
        core["year"] = core["entry_ts"].dt.year
        results["core_breakdowns"] = {
            "by_instrument": metrics_by_group(core, "instrument").to_dict(orient="records"),
            "by_model": metrics_by_group(core, "model").to_dict(orient="records"),
            "by_year": metrics_by_group(core, "year").to_dict(orient="records"),
            "by_regime": metrics_by_group(core, "bias").to_dict(orient="records"),
            "by_reason": metrics_by_group(core, "reason").to_dict(orient="records"),
        }
    if not robust.empty:
        robust["year"] = robust["entry_ts"].dt.year
        results["robust_breakdowns"] = {
            "by_instrument": metrics_by_group(robust, "instrument").to_dict(orient="records"),
            "by_model": metrics_by_group(robust, "model").to_dict(orient="records"),
        }

    with open(os.path.join(REPORT_DIR, "mp1_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved mp1_results.json")


if __name__ == "__main__":
    main()
