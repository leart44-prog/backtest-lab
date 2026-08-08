"""Daily execution x WEEKLY big-brother coverage (v5 zones, declared configs).

Weekly zones from resample('W') bars (labels = week end, so the completed-
period lookup in htf_covered is causal by construction: a daily timestamp
maps to the last label <= ts, i.e. the last COMPLETED week).

Configs:
  W0  Daily BASE                      (reference: PF 0.91)
  W1  Daily + weekly coverage
  W2  Daily + valuation               (reference: PF 1.00)
  W3  Daily + valuation + coverage
  W4  Daily + valuation + fresh + coverage   (reference w/o cov: PF 1.05)
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import (UNIVERSE, asset_class, run_course_sd, valuation_score,
                        daily_zones_with_lifespan)
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
            "avg_r": round(float(r.mean()), 3)}


def main():
    have = {m["name"] for m in load_manifest()}
    names = [u for u in UNIVERSE if u in have]
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    daily, weekly, wzones = {}, {}, {}
    for u in names + list(set("6E 6B 6A 6N 6C 6S 6J".split()) & have):
        bars = load_bars(u)
        daily[u] = bars.resample("1D").agg(agg).dropna()
        if u in names:
            w = bars.resample("W").agg(agg).dropna()
            weekly[u] = w
            wzones[u] = daily_zones_with_lifespan(w)   # generic lifespan scan
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

    CONFIGS = {
        "W0_BASE":          dict(use_valuation=False, use_htf=False),
        "W1_COV":           dict(use_valuation=False, use_htf=True),
        "W2_VAL":           dict(use_valuation=True,  use_htf=False),
        "W3_VAL_COV":       dict(use_valuation=True,  use_htf=True),
        "W4_VAL_FRESH_COV": dict(use_valuation=True,  use_htf=True,
                                 fresh_mode="fresh_only"),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cname, extra in CONFIGS.items():
        kw = dict(fresh_mode="user", formations=(0, 1, 2, 3, 4),
                  zone_scanner=scan_v5_zones)
        kw.update(extra)
        rows = []
        for u in names:
            rows.extend(run_course_sd(u, daily[u], scores[u], t1s[u],
                                      wzones[u], weekly[u].index, **kw))
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

    with open(os.path.join(REPORT_DIR, "weekly_coverage_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved weekly_coverage_results.json")


if __name__ == "__main__":
    main()
