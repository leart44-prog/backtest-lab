"""OTC S&D Zoning v3 (user's new indicator, chart settings) — daily backtest.

Declared BEFORE running; all cells reported. Universe/data/valuation/costs
identical to the detector shootout (40 instruments, daily resample of the
4H data, 2013-2026, IS/OOS split 2021-01-01).

Matrix:
  A) Strict convention (comparable with every previous study; costs on,
     one position per instrument, same-bar stopout = -1R, entry-bar
     favorable follow-through ignored):
       {BASE, VAL} x TP {1.0, 2.0, 2.5} R,  SL 33.33% beyond distal
     + formation breakdown (RBR/DBR/RBD/DBD) for BASE|2.5 and VAL|2.5.
  B) Pine-ledger replication (what the indicator's chart table computes:
     fill at raw proximal, same-bar TP counts, Loss first, no costs, no
     position limit): {BASE, VAL} x targets (1R, 2R).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .course_sd import UNIVERSE, asset_class, valuation_score
from .otc_v3_zones import collect_fills, eval_strict, eval_ledger
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "otc_v3")
FORM = {1: "RBR", 2: "DBR", 3: "RBD", 4: "DBD"}


def stats(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {"n": 0}
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    return {"n": int(len(r)), "wr": round(float(wins.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None,
            "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1)}


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
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

    fills = {u: collect_fills(daily[u]) for u in names}
    n_fills = sum(len(f) for f in fills.values())
    print(f"fills (first tests) across universe: {n_fills}")

    split = pd.Timestamp("2021-01-01", tz="UTC")
    results = {"n_fills": n_fills}

    # A) strict convention
    for cfg_name, use_val in (("BASE", False), ("VAL", True)):
        for tp in (1.0, 2.0, 2.5):
            rows = []
            for u in names:
                rows.extend(eval_strict(u, daily[u], fills[u], scores[u], t1s[u],
                                        use_valuation=use_val, target_r=tp))
            tdf = pd.DataFrame(rows)
            key = f"{cfg_name}|TP{tp}"
            if tdf.empty:
                results[key] = {"all": {"n": 0}}
                print(f"{key}: 0 trades")
                continue
            tdf = tdf.sort_values("ts")
            weeks = (tdf["ts"].max() - tdf["ts"].min()).days / 7
            res = {"all": stats(tdf["r"].to_numpy()),
                   "trades_per_week": round(len(tdf) / max(weeks, 1), 2),
                   "IS": stats(tdf[tdf["ts"] < split]["r"].to_numpy()),
                   "OOS": stats(tdf[tdf["ts"] >= split]["r"].to_numpy())}
            if tp == 2.5:
                res["formations"] = {FORM[fc]: stats(tdf[tdf["fcode"] == fc]["r"].to_numpy())
                                     for fc in (1, 2, 3, 4)}
            results[key] = res
            a = res["all"]
            print(f"{key}: n={a['n']} wr={a.get('wr')} pf={a.get('pf')} "
                  f"avgR={a.get('avg_r')} tpw={res['trades_per_week']} "
                  f"IS={res['IS'].get('pf')} OOS={res['OOS'].get('pf')}")

    # B) Pine-ledger replication
    for cfg_name, use_val in (("LEDGER_BASE", False), ("LEDGER_VAL", True)):
        rows = []
        for u in names:
            rows.extend(eval_ledger(daily[u], fills[u], scores[u], t1s[u],
                                    use_valuation=use_val))
        ldf = pd.DataFrame(rows)
        res = {}
        for tag, tr in (("r1", 1.0), ("r2", 2.0)):
            rr = ldf[tag].dropna().to_numpy(dtype=float)
            res[f"target_{tr}R"] = stats(rr)
            res[f"target_{tr}R"]["open_at_eos"] = int(ldf[tag].isna().sum())
        results[cfg_name] = res
        print(f"{cfg_name}: 1R -> {res['target_1.0R']} | 2R -> {res['target_2.0R']}")

    with open(os.path.join(REPORT_DIR, "otc_v3_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved otc_v3_results.json")


if __name__ == "__main__":
    main()
