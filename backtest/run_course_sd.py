"""Runner: course S/D + valuation backtest over the declared config matrix.

Declared BEFORE looking at results:
  C1  BASE        zones only, user management (limit@proximal, SL 25% beyond
                  distal, TP 2.5R, fresh or 1 touch <=25% pen, stacked->distal)
  C2  +VAL        C1 + valuation gate (demand only undervalued, supply only
                  overvalued; class presets t1 = 60/70/80)
  C3  +HTF        C1 + daily big-brother coverage
  C4  +VAL+HTF    both gates
  C5  FRESH_ONLY  C2 with strictly fresh zones
  C6  VAL_STRONG  C2 with t2-level gate (t1+10..15 -> stricter)
Split per asset class and IS (2013-2020) / OOS (2021-2026). All cells reported.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import (UNIVERSE, asset_class, run_course_sd, valuation_score,
                        daily_zones_with_lifespan)
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "course_sd")
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
    print(f"{len(names)} instruments")

    # preload bars, daily resample, futures series, class baskets
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
        baskets[klass] = pd.concat(norm, axis=1).ffill().mean(axis=1)

    scores, t1s = {}, {}
    for u in names:
        s, t1 = valuation_score(u, bars[u], fut, baskets)
        scores[u] = s
        t1s[u] = t1

    CONFIGS = {
        "C1_BASE":      dict(use_valuation=False, use_htf=False, fresh_mode="user"),
        "C2_VAL":       dict(use_valuation=True,  use_htf=False, fresh_mode="user"),
        "C3_HTF":       dict(use_valuation=False, use_htf=True,  fresh_mode="user"),
        "C4_VAL_HTF":   dict(use_valuation=True,  use_htf=True,  fresh_mode="user"),
        "C5_FRESH":     dict(use_valuation=True,  use_htf=False, fresh_mode="fresh_only"),
        "C6_VALSTRONG": dict(use_valuation=True,  use_htf=False, fresh_mode="user", t_shift=15.0),
    }

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {}
    for cname, cfg in CONFIGS.items():
        t_shift = cfg.pop("t_shift", 0.0)
        rows = []
        for u in names:
            rows.extend(run_course_sd(
                u, bars[u], scores[u], t1s[u] + t_shift,
                dzones[u], daily[u].index, **cfg))
        cfg["t_shift"] = t_shift
        tdf = pd.DataFrame(rows)
        if tdf.empty:
            results[cname] = {"all": {"n": 0}}
            print(f"{cname}: 0 trades")
            continue
        tdf = tdf.sort_values("ts").reset_index(drop=True)
        tdf.to_csv(os.path.join(REPORT_DIR, f"{cname}_trades.csv"), index=False)
        r = tdf["r"].to_numpy()
        weeks = (tdf["ts"].max() - tdf["ts"].min()).days / 7
        res = {"all": stats(r),
               "trades_per_week": round(len(tdf) / max(weeks, 1), 2),
               "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
               "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy()),
               "by_class": {k: stats(g["r"].to_numpy()) for k, g in tdf.groupby("klass")},
               "by_side": {k: stats(g["r"].to_numpy()) for k, g in tdf.groupby("side")},
               "by_fcode": {int(k): stats(g["r"].to_numpy()) for k, g in tdf.groupby("fcode")}}
        results[cname] = res
        a = res["all"]
        print(f"{cname}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
              f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
              f"IS_pf={res['IS'].get('pf')} OOS_pf={res['OOS'].get('pf')}")

    with open(os.path.join(REPORT_DIR, "course_sd_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved course_sd_results.json")


if __name__ == "__main__":
    main()
