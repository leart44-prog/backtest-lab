"""Replication of the mentor's OTC zone studies on our data.

Protocol per the PDFs + the indicator's study preset (§8.8):
  - V3 base behaviour: NO gap integration, NO leg-in wick extension, NO
    pivot integration, NO 2-candle leg-out, NO speed bump, overlap keep-all
  - proximal = Preferred, skip 0, stop 33.33% beyond distal
  - fresh zones only, first touch fills, targets 1:1 and 1:2 evaluated
    separately, ledger convention (resolution starts on the fill bar,
    Loss first on same-bar SL+TP), no costs, no position limit
  - weekend bars removed (261 bars/year), last 10 years of data

Universes (matching the studies as far as our data allows):
  - MAJORS: 6E 6B 6J 6S 6A 6C 6N daily futures (their 8 dollar pairs
    minus DXY, same orientation)
  - CROSSES: the same 21 cross pairs as the crosses study
Then the honest-convention counterfactual on the identical fills
(entry-bar favorable follow-through ignored, same-bar stopout = -1R,
one position per instrument), frictionless and with costs.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .otc_v3_zones import MENTOR_CFG, collect_fills, eval_ledger, eval_strict
from .data import load_bars, load_manifest

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "otc_v3")

MAJORS = ["6E", "6B", "6J", "6S", "6A", "6C", "6N"]
CROSSES = ["EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
           "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
           "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
           "NZDJPY", "NZDCHF", "NZDCAD",
           "CADJPY", "CADCHF", "CHFJPY"]


def ledger_stats(rows: list[dict], tag: str) -> dict:
    r = np.array([x[tag] for x in rows if x[tag] is not None], dtype=float)
    if len(r) == 0:
        return {"n": 0}
    wins = r > 0
    return {"n": int(len(r)), "wr": round(float(wins.mean()), 3),
            "avg_r": round(float(r.mean()), 3)}


def strict_stats(trades: list[dict]) -> dict:
    r = np.array([t["r"] for t in trades], dtype=float)
    if len(r) == 0:
        return {"n": 0}
    wins = r > 0
    pos, neg = r[wins].sum(), -r[~wins].sum()
    return {"n": int(len(r)), "wr": round(float(wins.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None,
            "avg_r": round(float(r.mean()), 3)}


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    have = {m["name"] for m in load_manifest()}
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    results = {}

    for uni_name, uni in (("MAJORS_FUT", MAJORS), ("CROSSES", CROSSES)):
        names = [u for u in uni if u in have]
        daily, fills, zcounts = {}, {}, {}
        for u in names:
            d = load_bars(u).resample("1D").agg(agg).dropna()
            d = d[d.index.dayofweek <= 4]                     # 261 bars/year
            d = d[d.index >= d.index[-1] - pd.DateOffset(years=10)]
            daily[u] = d
            cnt = {}
            fills[u] = collect_fills(d, cfg=MENTOR_CFG, counts=cnt)
            zcounts[u] = cnt["zones"]

        per_pair = {}
        pooled = []
        for u in names:
            led = eval_ledger(daily[u], fills[u], None, 0.0, use_valuation=False)
            pooled.extend(led)
            per_pair[u] = {"zones": zcounts[u], "fills": len(fills[u]),
                           "t11": ledger_stats(led, "r1"),
                           "t12": ledger_stats(led, "r2")}
            p = per_pair[u]
            print(f"{uni_name} {u:7s}: zones={p['zones']:4d} fills={p['fills']:4d} "
                  f"1:1 n={p['t11'].get('n',0):4d} wr={p['t11'].get('wr')} "
                  f"avgR={p['t11'].get('avg_r')} | 1:2 wr={p['t12'].get('wr')} "
                  f"avgR={p['t12'].get('avg_r')}")
        pool = {"t11": ledger_stats(pooled, "r1"), "t12": ledger_stats(pooled, "r2"),
                "zones": int(sum(zcounts.values()))}
        print(f"{uni_name} POOLED: zones={pool['zones']} "
              f"1:1 n={pool['t11']['n']} wr={pool['t11']['wr']} avgR={pool['t11']['avg_r']} | "
              f"1:2 n={pool['t12']['n']} wr={pool['t12']['wr']} avgR={pool['t12']['avg_r']}")

        # honest-convention counterfactual on the identical fills
        strict = {}
        for label, fl, tp in (("strict_free_1R", True, 1.0), ("strict_free_2R", True, 2.0),
                              ("strict_cost_1R", False, 1.0), ("strict_cost_2R", False, 2.0)):
            rows = []
            for u in names:
                rows.extend(eval_strict(u, daily[u], fills[u], None, 0.0,
                                        use_valuation=False, target_r=tp,
                                        frictionless=fl))
            strict[label] = strict_stats(rows)
            s = strict[label]
            print(f"  {label}: n={s['n']} wr={s.get('wr')} pf={s.get('pf')} avgR={s.get('avg_r')}")

        results[uni_name] = {"per_pair": per_pair, "pooled": pool, "strict": strict}

    with open(os.path.join(REPORT_DIR, "mentor_replication.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved mentor_replication.json")


if __name__ == "__main__":
    main()
