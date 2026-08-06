"""Test the untested Bernd-spec components as individual gates.

Baseline D0 = C2 (zones + valuation gate, user's management) — the best
config from the main study. Each new gate added individually, then combined:

  D0  baseline (= C2 rerun)
  D1  + location gate (5 bands from daily zones; long only <0.33 of span,
      short only >0.66, equilibrium excluded)
  D2  + trend gate (daily pivot structure; counter-trend needs clean arrival)
  D3  + profit-margin gate (>=2R headroom to nearest opposing LTF zone)
  D4  + arrival gate (impulsive approach, no opposing zone en route)
  D5  + all four
  D6  D5 restricted to reversal formations (DBR+RBD, prior finding)

All declared before running; all cells reported.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import (UNIVERSE, asset_class, run_course_sd, valuation_score,
                        daily_zones_with_lifespan, daily_pivot_trend)
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "course_sd")


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

    bars, daily, dzones, dtrend = {}, {}, {}, {}
    for u in names + list(set("6E 6B 6A 6N 6C 6S 6J".split()) & have):
        bars[u] = load_bars(u)
    fut = {k: bars[k]["close"] for k in ("6E", "6B", "6A", "6N", "6C", "6S", "6J") if k in bars}
    for u in names:
        d = bars[u].resample("1D").agg({"open": "first", "high": "max",
                                        "low": "min", "close": "last"}).dropna()
        daily[u] = d
        dzones[u] = daily_zones_with_lifespan(d)
        dtrend[u] = daily_pivot_trend(d)

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

    CONFIGS = {
        "D0_baseline": dict(),
        "D1_location": dict(location_gate=True),
        "D2_trend":    dict(trend_gate=True),
        "D3_pm":       dict(pm_gate=True),
        "D4_arrival":  dict(arrival_gate=True),
        "D5_all":      dict(location_gate=True, trend_gate=True, pm_gate=True,
                            arrival_gate=True),
        "D6_all_rev":  dict(location_gate=True, trend_gate=True, pm_gate=True,
                            arrival_gate=True, formations=(2, 3)),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cname, extra in CONFIGS.items():
        rows = []
        for u in names:
            rows.extend(run_course_sd(
                u, bars[u], scores[u], t1s[u], dzones[u], daily[u].index,
                use_valuation=True, use_htf=False, fresh_mode="user",
                daily_trend=dtrend[u], **extra))
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
               "by_class": {k: stats(g["r"].to_numpy()) for k, g in tdf.groupby("klass")}}
        results[cname] = res
        a = res["all"]
        print(f"{cname}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
              f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
              f"IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')}")

    with open(os.path.join(REPORT_DIR, "bernd_gates_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved bernd_gates_results.json")


if __name__ == "__main__":
    main()
