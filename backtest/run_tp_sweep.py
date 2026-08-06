"""TP sweep on the daily v5 configs: 1.0 / 1.5 / 2.0 / 2.5 / 3.0 R.

Declared before running; all cells reported. Everything else identical to
the detector shootout (v5 zones, daily, honest fills, user's management).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import UNIVERSE, asset_class, run_course_sd, valuation_score
from .v5_zones import scan_v5_zones
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "detector_shootout")


def stats(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {"n": 0}
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    return {"n": int(len(r)), "wr": round(float(wins.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None,
            "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1)}


def main():
    have = {m["name"] for m in load_manifest()}
    names = [u for u in UNIVERSE if u in have]
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    daily = {}
    for u in names + list(set("6E 6B 6A 6N 6C 6S 6J".split()) & have):
        daily[u] = load_bars(u).resample("1D").agg(agg).dropna()
    fut = {k: daily[k]["close"] for k in ("6E", "6B", "6A", "6N", "6C", "6S", "6J") if k in daily}
    baskets = {}
    for klass in ("indices", "metals", "commodities"):
        members = [u for u in names if asset_class(u) == klass]
        norm = [daily[u]["close"] / daily[u]["close"].iloc[0] for u in members]
        baskets[klass] = pd.concat(norm, axis=1, sort=False).ffill().mean(axis=1)
    scores, t1s = {}, {}
    for u in names:
        s, t1 = valuation_score(u, daily[u], fut, baskets)
        scores[u] = s
        t1s[u] = t1

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cfg_name, cfg in (("BASE", dict(use_valuation=False, fresh_mode="user")),
                          ("VAL_FRESH", dict(use_valuation=True, fresh_mode="fresh_only"))):
        for tp in (1.0, 1.5, 2.0, 2.5, 3.0):
            rows = []
            for u in names:
                rows.extend(run_course_sd(
                    u, daily[u], scores[u], t1s[u], None, None,
                    use_htf=False, formations=(0, 1, 2, 3, 4),
                    zone_scanner=scan_v5_zones, target_r=tp, **cfg))
            tdf = pd.DataFrame(rows).sort_values("ts")
            key = f"{cfg_name}|TP{tp}"
            res = {"all": stats(tdf["r"].to_numpy()),
                   "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
                   "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy())}
            results[key] = res
            a = res["all"]
            print(f"{key}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
                  f"avgR={a.get('avg_r')} IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')}")

    with open(os.path.join(REPORT_DIR, "tp_sweep_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved tp_sweep_results.json")


if __name__ == "__main__":
    main()
