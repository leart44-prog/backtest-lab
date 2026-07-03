"""Corrected primary experiment per audit: paired per-signal order-type test.

Audit fixes applied relative to run_entry_models.py:
  - NO position blocking: every signal is evaluated under every entry model
    on the identical signal set (pure paired design; capacity is a separate
    question).
  - replay() now applies the conservative same-bar rule to freshly moved
    BE stops (M4/M3/M5 were optimistic before).
  - SL levels use the last completed bar's ATR (no touch-bar ATR leak).
  - Commission charged per trade: r -= 2 * commission_pct * entry / risk.
  - Primary metric: per-signal R (unfilled signal = 0R), paired difference
    vs LIMIT, weekly block bootstrap CI (cross-instrument dependence).
  - Only the two pre-declared management variants: M2_fix3R, M4_chandelier.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest
from .entry_models import ENTRY_MODELS, fill_signal
from .run_trade_mgmt import FX_INDICES_METALS
from .sd_zones import prep_4h, find_zone_touches
from .trade_mgmt import replay

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "entry_models")
os.makedirs(REPORT_DIR, exist_ok=True)

MGMT = ("M2_fix3R", "M4_chandelier")


def main():
    have = {m["name"] for m in load_manifest()}
    names = [n for n in FX_INDICES_METALS if n in have]
    meta_by = {m["name"]: m for m in load_manifest()}

    rows = []
    for name in names:
        df = prep_4h(name)
        signals = find_zone_touches(name, df)
        meta = meta_by[name]
        cost = cost_for(name, meta.get("jpy", False), meta["type"],
                        meta["category"], meta.get("tick"))
        friction = cost.spread_price + cost.slippage_price
        for k, sig in enumerate(signals):
            sig_id = f"{name}#{k}"
            week = pd.Timestamp(sig["ts"]).strftime("%G-%V")
            for model in ENTRY_MODELS:
                fill = fill_signal(sig, df, model, friction)
                for v in MGMT:
                    if fill is None:
                        rows.append({"signal_id": sig_id, "instrument": name,
                                     "week": week, "entry_model": model,
                                     "variant": v, "filled": 0, "r": 0.0,
                                     "reason": "NO_FILL"})
                        continue
                    if fill["same_bar_stopout"]:
                        r = -1.0
                        reason = "SAME_BAR_SL"
                    else:
                        res = replay(df, fill["entry_i"], sig["side"],
                                     fill["entry"], fill["stop"], v,
                                     time_stop_bars=60)
                        r = res["r"]
                        reason = res["reason"]
                    risk = abs(fill["entry"] - fill["stop"])
                    comm_r = 2 * cost.commission_pct * fill["entry"] / risk
                    rows.append({"signal_id": sig_id, "instrument": name,
                                 "week": week, "entry_model": model,
                                 "variant": v, "filled": 1,
                                 "r": r - comm_r, "reason": reason})
        print(f"  {name}: {len(signals)} signals")

    df_all = pd.DataFrame(rows)
    df_all.to_csv(os.path.join(REPORT_DIR, "verify_paired.csv"), index=False)

    # ── summary: per-signal R per model x variant ──
    results = {}
    rng = np.random.default_rng(7)
    for v in MGMT:
        sub = df_all[df_all["variant"] == v]
        piv = sub.pivot_table(index=["signal_id", "week"], columns="entry_model",
                              values="r", aggfunc="first")
        piv = piv.reset_index()
        weeks = piv["week"].to_numpy()
        uniq_weeks = np.unique(weeks)
        summary = {}
        for model in ENTRY_MODELS:
            x = piv[model].to_numpy()
            filled = sub[(sub["entry_model"] == model) & (sub["filled"] == 1)]
            fr = len(filled) / len(piv)
            wins = (filled["r"] > 0).sum()
            pos = filled.loc[filled["r"] > 0, "r"].sum()
            neg = -filled.loc[filled["r"] <= 0, "r"].sum()
            summary[model] = {
                "mean_r_per_signal": round(float(np.mean(x)), 4),
                "fill_rate": round(fr, 3),
                "pf_per_fill": round(float(pos / neg), 3) if neg > 0 else None,
                "mean_r_per_fill": round(float(filled["r"].mean()), 4) if len(filled) else None,
                "win_rate_per_fill": round(float(wins / len(filled)), 3) if len(filled) else None,
            }
            # paired diff vs LIMIT with weekly block bootstrap
            if model != "LIMIT":
                d = piv[model].to_numpy() - piv["LIMIT"].to_numpy()
                boots = np.empty(2000)
                for b in range(2000):
                    wk = rng.choice(uniq_weeks, size=len(uniq_weeks), replace=True)
                    mask_sum = 0.0
                    cnt = 0
                    for w in wk:
                        sel = d[weeks == w]
                        mask_sum += sel.sum()
                        cnt += len(sel)
                    boots[b] = mask_sum / max(cnt, 1)
                lo, hi = np.percentile(boots, [2.5, 97.5])
                summary[model]["paired_diff_vs_LIMIT"] = {
                    "mean": round(float(np.mean(d)), 4),
                    "ci95": [round(float(lo), 4), round(float(hi), 4)],
                    "p_gt_0": round(float(np.mean(boots > 0)), 3),
                }
        results[v] = summary
        print(f"\n{v}:")
        for model, s in summary.items():
            pd_str = ""
            if "paired_diff_vs_LIMIT" in s:
                p = s["paired_diff_vs_LIMIT"]
                pd_str = f" | diff vs LIMIT {p['mean']:+.4f} CI{p['ci95']}"
            print(f"  {model:14s} R/signal={s['mean_r_per_signal']:+.4f} "
                  f"fill={s['fill_rate']:.2f} pf/fill={s['pf_per_fill']}{pd_str}")

    with open(os.path.join(REPORT_DIR, "verify_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved verify_results.json")


if __name__ == "__main__":
    main()
