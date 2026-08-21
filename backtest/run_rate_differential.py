"""Pair-specific policy-rate differentials vs the zone-reversal config.

Declared before running: M1 = |rate_base - rate_quote| at entry, split at
1.0%. M2 = |12-month change of the differential|, split at 0.5%. M3 = both
(compressed AND stable). Configs: REVERSALS and VAL_FRESH (age500) on
Dukascopy daily FX 2003-2026. Rates: backtest/policy_rates.py (documented
decision history, monthly precision, effective month+1 = conservative lag;
NZ exact from TradingView, US endpoint verified).

Result (see reports/detector_shootout/rate_differential_results.md):
level M1 separates nothing (1.21 vs 1.19 on reversals); STABILITY M2
separates clearly on reversals (stable 1.47, n=71 vs moving 0.95, n=76),
consistent with the Fed-phase finding (edge when rates are parked). On
VAL_FRESH no separation -> effect is reversal-specific and n is small.
"""
import os
import numpy as np
import pandas as pd

from .validate_oos_dukascopy import CROSSES, MAJORS, load_daily
from .course_sd import run_course_sd, valuation_score
from .v5_zones import scan_v5_zones
from .policy_rates import rate_series


def stats(r):
    if len(r) == 0:
        return {"n": 0}
    w = r > 0
    pos, neg = r[w].sum(), -r[~w].sum()
    return {"n": int(len(r)), "avgR": round(float(r.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None}


def main():
    daily = {p: load_daily(p) for p in CROSSES + MAJORS}
    daily = {p: d for p, d in daily.items() if len(d) > 500}
    leg = {"6E": ("EURUSD", False), "6B": ("GBPUSD", False), "6A": ("AUDUSD", False),
           "6N": ("NZDUSD", False), "6C": ("USDCAD", True), "6S": ("USDCHF", True),
           "6J": ("USDJPY", True)}
    fut = {c: (1.0 / daily[p]["close"] if inv else daily[p]["close"])
           for c, (p, inv) in leg.items()}
    diffs = {p: rate_series(p[:3], daily[p].index) - rate_series(p[3:], daily[p].index)
             for p in daily}

    for label, formations in (("REVERSALS", (2, 3)), ("VAL_FRESH", (0, 1, 2, 3, 4))):
        rows = []
        for u in daily:
            s, t1 = valuation_score(u, daily[u], fut, {})
            for tr in run_course_sd(u, daily[u], s, t1, None, None,
                                    use_valuation=True, use_htf=False,
                                    fresh_mode="fresh_only",
                                    zone_scanner=scan_v5_zones, target_r=2.5,
                                    formations=formations, max_zone_age=500):
                d = diffs[u]
                i = min(d.index.searchsorted(tr["ts"]), len(d) - 1)
                tr["difflvl"] = abs(float(d.iloc[i]))
                tr["diffchg"] = abs(float(d.iloc[i] - d.iloc[max(0, i - 252)]))
                rows.append(tr)
        t = pd.DataFrame(rows).sort_values("ts")
        print(f"\n=== {label} (n={len(t)}) ===")
        print("M1 |Diff|<1%: ", stats(t[t.difflvl < 1.0]["r"].to_numpy()),
              " >=1%:", stats(t[t.difflvl >= 1.0]["r"].to_numpy()))
        print("M2 stabil:    ", stats(t[t.diffchg < 0.5]["r"].to_numpy()),
              " bewegt:", stats(t[t.diffchg >= 0.5]["r"].to_numpy()))
        good = (t.difflvl < 1.0) & (t.diffchg < 0.5)
        print("M3 beides:    ", stats(t[good]["r"].to_numpy()),
              " Rest:", stats(t[~good]["r"].to_numpy()))


if __name__ == "__main__":
    main()
