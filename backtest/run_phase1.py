"""Phase 1 master runner.

- Loads all 40 Phase-1 instruments
- Runs three variants (V1, V2, V3) and each individual setup A/B/C/D
- Splits IS (2013-2020) / OOS (2021-2026)
- Computes metrics, per-instrument, per-year, per-model
- Runs Monte Carlo on V1 winner
- Saves reports + charts to reports/phase1/
"""
from __future__ import annotations

import os
import time
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analytics import (
    compute_metrics, equity_curve, drawdown_series, monte_carlo,
    trades_to_df, metrics_by_group, split_in_out_sample,
)
from .costs import cost_for
from .data import phase1_instruments, load_instrument
from .engine import run_instrument, ExecutedTrade


REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "phase1")
os.makedirs(REPORT_DIR, exist_ok=True)

VARIANTS = {
    "V1_TrendOnly":  ("A", "C"),
    "V2_Balanced":   ("A", "B", "C"),
    "V3_Full":       ("A", "B", "C", "D"),
    "S_A":           ("A",),
    "S_B":           ("B",),
    "S_C":           ("C",),
    "S_D":           ("D",),
}


def _run_one_instrument(args):
    meta, setups = args
    try:
        inst = load_instrument(meta)
        cost = cost_for(inst.name, inst.jpy, inst.asset_type, inst.category, inst.tick)
        trades = run_instrument(inst, cost, enabled_setups=setups)
        return trades
    except Exception as e:
        print(f"  ERROR {meta['name']}: {e}")
        return []


def run_variant(variant_name: str, setups: tuple, metas: list[dict]) -> pd.DataFrame:
    t0 = time.time()
    all_trades: list[ExecutedTrade] = []
    args_list = [(m, setups) for m in metas]
    # Parallelize across instruments
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        futures = [ex.submit(_run_one_instrument, a) for a in args_list]
        for f in as_completed(futures):
            all_trades.extend(f.result())
    elapsed = time.time() - t0
    df = trades_to_df(all_trades)
    print(f"  {variant_name}: {len(df)} trades in {elapsed:.1f}s")
    return df


def plot_equity_and_dd(df_trades: pd.DataFrame, title: str, save_path: str,
                       start_equity: float = 100_000.0, risk_pct: float = 0.005):
    if df_trades.empty:
        return
    eq = equity_curve(df_trades, start_equity, risk_pct)
    dd = drawdown_series(eq)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7),
                                    gridspec_kw={"height_ratios": [2, 1]}, sharex=True)
    ax1.plot(eq["ts"], eq["equity"], color="#1f77b4", linewidth=1.2)
    ax1.axhline(start_equity, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax1.set_title(f"{title} — Equity Curve")
    ax1.set_ylabel("Account ($)")
    ax1.grid(alpha=0.3)
    ax2.fill_between(dd["ts"], dd["dd_pct"], 0, color="#d62728", alpha=0.4)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=110)
    plt.close(fig)


def plot_monte_carlo(df_trades: pd.DataFrame, title: str, save_path: str,
                     start_equity: float = 100_000.0, risk_pct: float = 0.005,
                     n_runs: int = 1000, seed: int = 42):
    if df_trades.empty:
        return
    r = df_trades["r"].values
    n = len(r)
    rng = np.random.default_rng(seed)
    paths = np.zeros((n_runs, n + 1))
    for k in range(n_runs):
        shuffled = rng.choice(r, size=n, replace=True)
        cur = start_equity
        paths[k, 0] = cur
        for j, x in enumerate(shuffled):
            cur += x * risk_pct * cur
            paths[k, j + 1] = cur
    p5 = np.percentile(paths, 5, axis=0)
    p50 = np.percentile(paths, 50, axis=0)
    p95 = np.percentile(paths, 95, axis=0)
    x = np.arange(n + 1)
    fig, ax = plt.subplots(figsize=(11, 5))
    for k in range(min(100, n_runs)):
        ax.plot(x, paths[k], color="#cccccc", alpha=0.2, linewidth=0.5)
    ax.plot(x, p50, color="#1f77b4", linewidth=2, label="Median")
    ax.plot(x, p5, color="#d62728", linewidth=1.2, linestyle="--", label="5%")
    ax.plot(x, p95, color="#2ca02c", linewidth=1.2, linestyle="--", label="95%")
    ax.axhline(start_equity, color="gray", linestyle=":", linewidth=0.8)
    ax.set_title(f"{title} — Monte Carlo ({n_runs} runs)")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Account ($)")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=110)
    plt.close(fig)


def metrics_row(m) -> dict:
    return {
        "n_trades": m.n_trades,
        "win_rate": round(m.win_rate, 3),
        "avg_r": round(m.avg_r, 3),
        "avg_win_r": round(m.avg_win_r, 2),
        "avg_loss_r": round(m.avg_loss_r, 2),
        "profit_factor": round(m.profit_factor, 2) if np.isfinite(m.profit_factor) else "inf",
        "expectancy_r": round(m.expectancy_r, 3),
        "sum_r": round(m.sum_r, 1),
        "max_dd_pct": round(m.max_dd_pct, 2),
        "cagr_pct": round(m.cagr_pct, 2),
        "sharpe": round(m.sharpe, 2),
        "sortino": round(m.sortino, 2),
        "longest_loss_streak": m.longest_loss_streak,
        "longest_win_streak": m.longest_win_streak,
        "avg_hold_days": round(m.avg_hold_bars / 6, 1),
    }


def main():
    metas = phase1_instruments()
    print(f"Phase 1: {len(metas)} instruments")

    split_ts = pd.Timestamp("2021-01-01", tz="UTC")
    summary = {}
    all_trades_by_variant = {}

    for vname, setups in VARIANTS.items():
        print(f"\n=== {vname} {setups} ===")
        df = run_variant(vname, setups, metas)
        all_trades_by_variant[vname] = df
        if df.empty:
            summary[vname] = {}
            continue

        ins, oos = split_in_out_sample(df, split_ts)
        m_all = compute_metrics(df)
        m_ins = compute_metrics(ins)
        m_oos = compute_metrics(oos)

        summary[vname] = {
            "all":     metrics_row(m_all),
            "in_sample_2013_2020":  metrics_row(m_ins),
            "out_of_sample_2021_2026": metrics_row(m_oos),
        }

        # Charts only for the main variants (not individual setups)
        if vname in ("V1_TrendOnly", "V2_Balanced", "V3_Full"):
            plot_equity_and_dd(df, vname + " (full)",
                               os.path.join(REPORT_DIR, f"{vname}_equity.png"))
            plot_equity_and_dd(ins, vname + " (IS 2013-2020)",
                               os.path.join(REPORT_DIR, f"{vname}_IS_equity.png"))
            plot_equity_and_dd(oos, vname + " (OOS 2021-2026)",
                               os.path.join(REPORT_DIR, f"{vname}_OOS_equity.png"))

        # Save trade log
        df.to_csv(os.path.join(REPORT_DIR, f"{vname}_trades.csv"), index=False)

    # ── Monte Carlo on V1 ──
    v1 = all_trades_by_variant.get("V1_TrendOnly")
    mc_results = {}
    if v1 is not None and not v1.empty:
        mc_results["V1_TrendOnly_full"] = monte_carlo(v1["r"].values, n_runs=1000)
        plot_monte_carlo(v1, "V1_TrendOnly", os.path.join(REPORT_DIR, "V1_montecarlo.png"))

        v1_oos = v1[v1["entry_ts"] >= split_ts]
        if len(v1_oos) >= 20:
            mc_results["V1_TrendOnly_OOS"] = monte_carlo(v1_oos["r"].values, n_runs=1000)

    v2 = all_trades_by_variant.get("V2_Balanced")
    if v2 is not None and not v2.empty:
        mc_results["V2_Balanced_full"] = monte_carlo(v2["r"].values, n_runs=1000)
        plot_monte_carlo(v2, "V2_Balanced", os.path.join(REPORT_DIR, "V2_montecarlo.png"))

    v3 = all_trades_by_variant.get("V3_Full")
    if v3 is not None and not v3.empty:
        mc_results["V3_Full_full"] = monte_carlo(v3["r"].values, n_runs=1000)
        plot_monte_carlo(v3, "V3_Full", os.path.join(REPORT_DIR, "V3_montecarlo.png"))

    # ── Per-instrument / per-year / per-model breakdowns for the main variant ──
    breakdowns = {}
    for vname in ("V1_TrendOnly", "V2_Balanced", "V3_Full"):
        df = all_trades_by_variant[vname]
        if df.empty:
            continue
        df["year"] = df["entry_ts"].dt.year
        df["weekday"] = df["entry_ts"].dt.weekday
        breakdowns[vname] = {
            "by_instrument": metrics_by_group(df, "instrument").to_dict(orient="records"),
            "by_model":      metrics_by_group(df, "model").to_dict(orient="records"),
            "by_year":       metrics_by_group(df, "year").to_dict(orient="records"),
            "by_weekday":    metrics_by_group(df, "weekday").to_dict(orient="records"),
            "by_bias":       metrics_by_group(df, "bias").to_dict(orient="records"),
            "by_reason":     metrics_by_group(df, "reason").to_dict(orient="records"),
        }

    # ── Save summary ──
    out = {
        "summary_metrics": summary,
        "monte_carlo": mc_results,
        "breakdowns": breakdowns,
    }
    with open(os.path.join(REPORT_DIR, "phase1_results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nSaved phase1_results.json")


if __name__ == "__main__":
    main()
