"""S&D Zones [v4] on DAILY bars — same configs as the 4H study.

Fidelity notes:
  - Pine effMax rule: on daily charts max base candles = min(maxBase, 3).
  - Valuation score computed on daily bars (chart-TF semantics of the
    indicator); FX futures resampled to daily closes.
  - Engine, management (limit@proximal, SL 25% beyond distal, TP 2.5R,
    fresh/1-touch-25%), fills and costs unchanged.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import (UNIVERSE, asset_class, run_course_sd, valuation_score)
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


def daily_scanner(df):
    return scan_v4_zones(df, max_base=3)   # Pine effMax rule on daily


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
        "D1D_BASE":        dict(use_valuation=False),
        "D1D_VAL":         dict(use_valuation=True),
        "D1D_VAL_FRESH":   dict(use_valuation=True, fresh_mode="fresh_only"),
        "D1D_VAL_ARRIVAL": dict(use_valuation=True, arrival_gate=True),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cname, extra in CONFIGS.items():
        kw = dict(use_htf=False, fresh_mode="user", formations=FORMS_ALL,
                  zone_scanner=daily_scanner)
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
        tdf = tdf.sort_values("ts").reset_index(drop=True)
        tdf.to_csv(os.path.join(REPORT_DIR, f"{cname}_trades.csv"), index=False)
        weeks = (tdf["ts"].max() - tdf["ts"].min()).days / 7
        res = {"all": stats(tdf["r"].to_numpy()),
               "trades_per_week": round(len(tdf) / max(weeks, 1), 2),
               "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
               "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy()),
               "by_class": {k: stats(g["r"].to_numpy()) for k, g in tdf.groupby("klass")},
               "by_fcode": {int(k): stats(g["r"].to_numpy()) for k, g in tdf.groupby("fcode")},
               "avg_hold_days": round(float(tdf["bars"].mean()), 1)}
        results[cname] = res
        a = res["all"]
        print(f"{cname}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
              f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
              f"IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')} "
              f"holdD={res['avg_hold_days']}")

    with open(os.path.join(REPORT_DIR, "v4_daily_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved v4_daily_results.json")


if __name__ == "__main__":
    main()
