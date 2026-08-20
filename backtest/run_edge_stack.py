"""Edge search under the constraint 'limit orders stay': two declared tests
on the daily v5 reference config (VAL_FRESH, TP 2.5R, honest fills, costs).

A) Quality stacking of the two qualifiers that showed positive effects in
   earlier independent studies (arrival +0.17R, reversal formations
   DBR/RBD > continuations):
     A1 VAL_FRESH                (reference, PF 1.05)
     A2 VAL_FRESH + arrival
     A3 VAL_FRESH + reversals only (DBR/RBD)
     A4 VAL_FRESH + arrival + reversals
   NOTE: this stacks filters that were selected as best-in-study — the
   combination is confirmatory only if OOS holds up; n will be small.

B) Entry depth (win-rate lever that keeps limit orders): limit placed
   0% / 25% / 50% of the zone height INSIDE the zone. Deeper = fewer
   fills, smaller risk per trade, filters shallow touches.
     B0 depth 0.00 (reference)  B1 depth 0.25  B2 depth 0.50

All cells reported; IS/OOS split 2021-01-01.
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

    base = dict(use_valuation=True, use_htf=False, fresh_mode="fresh_only",
                zone_scanner=scan_v5_zones, target_r=2.5)
    CELLS = {
        "A1_VAL_FRESH":         dict(formations=(0, 1, 2, 3, 4)),
        "A2_+arrival":          dict(formations=(0, 1, 2, 3, 4), arrival_gate=True),
        "A3_+reversals":        dict(formations=(2, 3)),
        "A4_+arrival+revers":   dict(formations=(2, 3), arrival_gate=True),
        "B1_depth25":           dict(formations=(0, 1, 2, 3, 4), entry_depth=0.25),
        "B2_depth50":           dict(formations=(0, 1, 2, 3, 4), entry_depth=0.50),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cname, extra in CELLS.items():
        kw = dict(base)
        kw.update(extra)
        rows = []
        for u in names:
            rows.extend(run_course_sd(u, daily[u], scores[u], t1s[u],
                                      None, None, **kw))
        tdf = pd.DataFrame(rows)
        if tdf.empty:
            results[cname] = {"all": {"n": 0}}
            print(f"{cname}: 0 trades")
            continue
        tdf = tdf.sort_values("ts")
        weeks = (tdf["ts"].max() - tdf["ts"].min()).days / 7
        res = {"all": stats(tdf["r"].to_numpy()),
               "trades_per_week": round(len(tdf) / max(weeks, 1), 2),
               "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
               "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy())}
        results[cname] = res
        a = res["all"]
        print(f"{cname}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
              f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
              f"IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')}")

    with open(os.path.join(REPORT_DIR, "edge_stack_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved edge_stack_results.json")


if __name__ == "__main__":
    main()
