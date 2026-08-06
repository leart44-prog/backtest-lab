"""Detector shootout on DAILY bars: course vs v4 vs v5-synthesis.

Same engine, management, costs, valuation for all three — only the detector
changes. Declared configs per detector: BASE, +VAL, +VAL_FRESH; plus v5
LoL-only (with valuation) to measure the level-on-level idea.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import (UNIVERSE, asset_class, run_course_sd, valuation_score,
                        scan_zones)
from .v4_zones import scan_v4_zones
from .v5_zones import scan_v5_zones, scan_v5_lol_only
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "detector_shootout")
os.makedirs(REPORT_DIR, exist_ok=True)


def stats(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {"n": 0}
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    return {"n": int(len(r)), "wr": round(float(wins.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None,
            "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1)}


SCANNERS = {
    "course": lambda df: scan_zones(df),
    "v4":     lambda df: scan_v4_zones(df, max_base=3),   # Pine daily effMax rule
    "v5":     lambda df: scan_v5_zones(df),
    "v5lol":  scan_v5_lol_only,
}


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

    FORMS_ALL = (0, 1, 2, 3, 4)
    CONFIGS = {
        "BASE":      dict(use_valuation=False),
        "VAL":       dict(use_valuation=True),
        "VAL_FRESH": dict(use_valuation=True, fresh_mode="fresh_only"),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for det, scanner in SCANNERS.items():
        cfgs = {"VAL": CONFIGS["VAL"]} if det == "v5lol" else CONFIGS
        for cname, extra in cfgs.items():
            key = f"{det}|{cname}"
            kw = dict(use_htf=False, fresh_mode="user", formations=FORMS_ALL,
                      zone_scanner=scanner)
            kw.update(extra)
            rows = []
            for u in names:
                rows.extend(run_course_sd(u, daily[u], scores[u], t1s[u],
                                          None, None, **kw))
            tdf = pd.DataFrame(rows)
            if tdf.empty:
                results[key] = {"all": {"n": 0}}
                print(f"{key}: 0 trades")
                continue
            tdf = tdf.sort_values("ts").reset_index(drop=True)
            tdf.to_csv(os.path.join(REPORT_DIR, f"{det}_{cname}_trades.csv"),
                       index=False)
            weeks = (tdf["ts"].max() - tdf["ts"].min()).days / 7
            res = {"all": stats(tdf["r"].to_numpy()),
                   "trades_per_week": round(len(tdf) / max(weeks, 1), 2),
                   "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
                   "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy()),
                   "by_class": {k: stats(g["r"].to_numpy()) for k, g in tdf.groupby("klass")},
                   "by_fcode": {int(k): stats(g["r"].to_numpy()) for k, g in tdf.groupby("fcode")}}
            results[key] = res
            a = res["all"]
            print(f"{key}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
                  f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
                  f"IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')}")

    with open(os.path.join(REPORT_DIR, "detector_shootout_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved detector_shootout_results.json")


if __name__ == "__main__":
    main()
