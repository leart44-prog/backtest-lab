"""S&D Zones [v4] study — same scope as the course-method study.

Only the zone DETECTOR changes (v4 scanner); trade rules, fills, costs,
valuation and engine are identical to the C-series, so differences are
attributable to the detector alone.

Configs (declared):
  V1  BASE          v4 zones, user management, no gates
  V2  VAL           + valuation gate (class presets 60/70/80)
  V3  VAL_FRESH     valuation + strictly fresh zones
  V4  VAL_ARRIVAL   valuation + arrival gate (best component from D-series)
Breakdowns: asset class, formation, IS/OOS, trades/week.
Reference: course-method C1 (PF 0.81) and C2 (PF 0.87).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import (UNIVERSE, asset_class, run_course_sd, valuation_score,
                        daily_zones_with_lifespan)
from .v4_zones import scan_v4_zones
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "v4_zones")
os.makedirs(REPORT_DIR, exist_ok=True)


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

    bars, daily, dzones = {}, {}, {}
    for u in names + list(set("6E 6B 6A 6N 6C 6S 6J".split()) & have):
        bars[u] = load_bars(u)
    fut = {k: bars[k]["close"] for k in ("6E", "6B", "6A", "6N", "6C", "6S", "6J") if k in bars}
    for u in names:
        d = bars[u].resample("1D").agg({"open": "first", "high": "max",
                                        "low": "min", "close": "last"}).dropna()
        daily[u] = d
        dzones[u] = daily_zones_with_lifespan(d)

    baskets = {}
    for klass in ("indices", "metals", "commodities"):
        members = [u for u in names if asset_class(u) == klass]
        norm = [bars[u]["close"] / bars[u]["close"].iloc[0] for u in members]
        baskets[klass] = pd.concat(norm, axis=1, sort=False).ffill().mean(axis=1)

    scores, t1s = {}, {}
    for u in names:
        s, t1 = valuation_score(u, bars[u], fut, baskets)
        scores[u] = s
        t1s[u] = t1

    FORMS_ALL = (0, 1, 2, 3, 4)   # v4 patterns can be empty -> fcode 0
    CONFIGS = {
        "V1_BASE":        dict(use_valuation=False),
        "V2_VAL":         dict(use_valuation=True),
        "V3_VAL_FRESH":   dict(use_valuation=True, fresh_mode="fresh_only"),
        "V4_VAL_ARRIVAL": dict(use_valuation=True, arrival_gate=True),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cname, extra in CONFIGS.items():
        kw = dict(use_htf=False, fresh_mode="user", formations=FORMS_ALL,
                  zone_scanner=scan_v4_zones)
        kw.update(extra)
        rows = []
        for u in names:
            rows.extend(run_course_sd(u, bars[u], scores[u], t1s[u],
                                      dzones[u], daily[u].index, **kw))
        tdf = pd.DataFrame(rows)
        if tdf.empty:
            results[cname] = {"all": {"n": 0}}
            print(f"{cname}: 0 trades")
            continue
        tdf = tdf.sort_values("ts").reset_index(drop=True)
        tdf.to_csv(os.path.join(REPORT_DIR, f"{cname}_trades.csv"), index=False)
        weeks = (tdf["ts"].max() - tdf["ts"].min()).days / 7
        res = {"all": stats(tdf["r"].to_numpy()),
               "trades_per_week": round(len(tdf) / max(weeks, 1), 2),
               "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
               "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy()),
               "by_class": {k: stats(g["r"].to_numpy()) for k, g in tdf.groupby("klass")},
               "by_fcode": {int(k): stats(g["r"].to_numpy()) for k, g in tdf.groupby("fcode")}}
        results[cname] = res
        a = res["all"]
        print(f"{cname}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
              f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
              f"IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')}")

    with open(os.path.join(REPORT_DIR, "v4_zones_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved v4_zones_results.json")


if __name__ == "__main__":
    main()
