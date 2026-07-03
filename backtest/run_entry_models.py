"""Runner: order-type comparison for S/D entries (limit vs stop vs close-confirm).

Same signals, same SL structure, same management variants — only the entry
order type changes. Includes a small a-priori sensitivity grid for
STOP_RECLAIM (buffer x validity), declared before looking at results:
default buf=0.10 ATR, validity=6 bars.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")

from .analytics import compute_metrics
from .costs import cost_for
from .data import load_manifest
from .entry_models import ENTRY_MODELS, fill_signal
from .run_phase1 import metrics_row
from .run_trade_mgmt import FX_INDICES_METALS
from .sd_zones import prep_4h, find_zone_touches
from .trade_mgmt import replay, VARIANTS

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "entry_models")
os.makedirs(REPORT_DIR, exist_ok=True)

BUSY_BARS = 60          # one position per instrument, ~10 trading days on 4H


def process_instrument(name: str, model: str, buf: float = 0.10,
                       validity: int = 6) -> tuple[list[dict], int]:
    """Run one entry model over one instrument. Returns (trade rows, n_signals)."""
    df = prep_4h(name)
    signals = find_zone_touches(name, df)
    meta = {m["name"]: m for m in load_manifest()}[name]
    cost = cost_for(name, meta.get("jpy", False), meta["type"], meta["category"],
                    meta.get("tick"))
    friction = cost.spread_price + cost.slippage_price

    rows = []
    busy_until = -1
    for sig in signals:
        if sig["touch_i"] <= busy_until:
            continue
        fill = fill_signal(sig, df, model, friction, buf_atr=buf, validity=validity)
        if fill is None:
            continue
        if fill["same_bar_stopout"]:
            for v in VARIANTS:
                rows.append({
                    "instrument": name, "entry_model": model, "variant": v,
                    "side": sig["side"], "entry_ts": df.index[fill["entry_i"]],
                    "r": -1.0, "bars_held": 0, "reason": "SAME_BAR_SL",
                })
            busy_until = fill["entry_i"]
            continue
        for v in VARIANTS:
            res = replay(df, fill["entry_i"], sig["side"], fill["entry"],
                         fill["stop"], v, time_stop_bars=BUSY_BARS)
            rows.append({
                "instrument": name, "entry_model": model, "variant": v,
                "side": sig["side"], "entry_ts": df.index[fill["entry_i"]],
                "r": res["r"], "bars_held": res["bars_held"],
                "reason": res["reason"],
            })
        busy_until = fill["entry_i"] + BUSY_BARS
    return rows, len(signals)


def summarize_model(df: pd.DataFrame, n_signals: int) -> dict:
    out = {"n_signals": n_signals}
    split = pd.Timestamp("2021-01-01", tz="UTC")
    for v in VARIANTS:
        sub = df[df["variant"] == v].copy()
        if sub.empty:
            continue
        sub["pnl_pct"] = sub["r"] * 0.005
        sub["entry_ts"] = pd.to_datetime(sub["entry_ts"], utc=True)
        sub["exit_ts"] = sub["entry_ts"]
        sub["bars"] = sub["bars_held"]
        sub = sub.sort_values("entry_ts")
        m = compute_metrics(sub)
        entry = {"all": metrics_row(m),
                 "fill_rate": round(len(sub) / max(n_signals, 1), 3),
                 "same_bar_stopouts": int((sub["reason"] == "SAME_BAR_SL").sum()),
                 "sum_r_per_signal": round(m.sum_r / max(n_signals, 1), 4)}
        ins = sub[sub["entry_ts"] < split]
        oos = sub[sub["entry_ts"] >= split]
        if len(ins) >= 20:
            entry["IS"] = metrics_row(compute_metrics(ins))
        if len(oos) >= 20:
            entry["OOS"] = metrics_row(compute_metrics(oos))
        out[v] = entry
    return out


def main():
    have = {m["name"] for m in load_manifest()}
    names = [n for n in FX_INDICES_METALS if n in have]

    results = {}
    all_rows = []
    for model in ENTRY_MODELS:
        rows_model = []
        n_signals_total = 0
        for name in names:
            rows, n_sig = process_instrument(name, model)
            rows_model.extend(rows)
            n_signals_total += n_sig
        dfm = pd.DataFrame(rows_model)
        all_rows.append(dfm)
        results[model] = summarize_model(dfm, n_signals_total)
        n_fills = len(dfm[dfm["variant"] == VARIANTS[0]])
        n_sbs = int((dfm[dfm["variant"] == VARIANTS[0]]["reason"] == "SAME_BAR_SL").sum())
        m2 = results[model].get("M2_fix3R", {}).get("all", {})
        m4 = results[model].get("M4_chandelier", {}).get("all", {})
        print(f"{model}: signals={n_signals_total} fills={n_fills} "
              f"same_bar={n_sbs} | M2 pf={m2.get('profit_factor')} "
              f"avgR={m2.get('avg_r')} | M4 pf={m4.get('profit_factor')} "
              f"avgR={m4.get('avg_r')}")

    pd.concat(all_rows, ignore_index=True).to_csv(
        os.path.join(REPORT_DIR, "entry_models_replay.csv"), index=False)

    # ── a-priori sensitivity grid for STOP_RECLAIM (M4 headline) ──
    print("\nSensitivity STOP_RECLAIM (buf x validity), M4/M2 avgR:")
    grid = {}
    for buf in (0.0, 0.10, 0.25):
        for validity in (3, 6, 12):
            rows_g = []
            n_sig_g = 0
            for name in names:
                rows, n_sig = process_instrument(name, "STOP_RECLAIM",
                                                 buf=buf, validity=validity)
                rows_g.extend(rows)
                n_sig_g += n_sig
            dfg = pd.DataFrame(rows_g)
            cell = {}
            for v in ("M2_fix3R", "M4_chandelier"):
                sub = dfg[dfg["variant"] == v]
                if len(sub) == 0:
                    continue
                r = sub["r"]
                pf = r[r > 0].sum() / abs(r[r <= 0].sum()) if (r <= 0).any() else float("inf")
                cell[v] = {"n": int(len(sub)), "pf": round(float(pf), 3),
                           "avg_r": round(float(r.mean()), 4)}
            grid[f"buf{buf}_val{validity}"] = cell
            m4c = cell.get("M4_chandelier", {})
            print(f"  buf={buf:4} val={validity:2d}: n={m4c.get('n')} "
                  f"pf={m4c.get('pf')} avgR={m4c.get('avg_r')}")
    results["sensitivity_STOP_RECLAIM"] = grid

    with open(os.path.join(REPORT_DIR, "entry_models_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved entry_models_results.json")


if __name__ == "__main__":
    main()
