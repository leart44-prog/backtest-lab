"""Independent verification of the TP sweep.

1. Reruns the sweep (engine now records entry/sl/tp per trade, CSVs saved).
2. A SEPARATE first-passage checker re-walks every single trade against the
   raw daily OHLC: which level (SL or TP) was touched first, starting the bar
   after entry, tie -> SL. Compares outcome and R with the engine's records.
3. Prints human-checkable sample trades (instrument, dates, exact prices)
   for manual TradingView verification.
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


def independent_first_passage(bars: pd.DataFrame, entry_i: int, side: str,
                              entry: float, sl: float, tp: float,
                              max_bars: int = 400) -> tuple[str, float, int]:
    """Fresh, minimal re-implementation: walk raw OHLC, first touch wins,
    same-bar tie -> SL. Entry bar itself: only SL counts (engine convention:
    same-bar stopout; favorable follow-through ignored)."""
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    n = len(bars)
    # entry bar check (same-bar stopout)
    if side == "long" and l[entry_i] <= sl:
        return "SAME_BAR_SL", -1.0, 0
    if side == "short" and h[entry_i] >= sl:
        return "SAME_BAR_SL", -1.0, 0
    risk = abs(entry - sl)
    end = min(n - 1, entry_i + max_bars)
    for j in range(entry_i + 1, end + 1):
        sl_hit = (l[j] <= sl) if side == "long" else (h[j] >= sl)
        tp_hit = (h[j] >= tp) if side == "long" else (l[j] <= tp)
        if sl_hit:                       # tie -> SL
            return "SL", -1.0, j - entry_i
        if tp_hit:
            r = (tp - entry) / risk if side == "long" else (entry - tp) / risk
            return "TP", r, j - entry_i
    r = ((c[end] - entry) / risk) if side == "long" else ((entry - c[end]) / risk)
    return "EOS", r, end - entry_i


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

    summary = {}
    for cfg_name, cfg in (("BASE", dict(use_valuation=False, fresh_mode="user")),
                          ("VAL_FRESH", dict(use_valuation=True, fresh_mode="fresh_only"))):
        for tp_mult in (1.0, 2.0, 2.5):
            rows = []
            for u in names:
                rows.extend(run_course_sd(
                    u, daily[u], scores[u], t1s[u], None, None,
                    use_htf=False, formations=(0, 1, 2, 3, 4),
                    zone_scanner=scan_v5_zones, target_r=tp_mult, **cfg))
            tdf = pd.DataFrame(rows)

            mismatch = 0
            checked = 0
            for _, t in tdf.iterrows():
                reason_i, r_i, bars_i = independent_first_passage(
                    daily[t["instrument"]], int(t["entry_i"]), t["side"],
                    float(t["entry"]), float(t["sl"]), float(t["tp"]))
                checked += 1
                # engine r includes commission; compare gross r and reason
                reason_match = (reason_i == t["reason"]) or \
                    (reason_i == "SL" and t["reason"] == "SL") or \
                    (reason_i == "TP" and t["reason"] == "TP")
                r_gross_engine = float(t["r"])  # includes -comm_r (tiny)
                r_close = abs(r_i - r_gross_engine) < 0.05
                if not (reason_match and r_close):
                    mismatch += 1

            r = tdf["r"].to_numpy()
            wins = r > 0
            pos, neg = r[wins].sum(), -r[~wins].sum()
            key = f"{cfg_name}|TP{tp_mult}"
            summary[key] = {
                "n": int(len(r)), "wr": round(float(wins.mean()), 3),
                "pf": round(float(pos / neg), 2),
                "verified": checked, "mismatches": mismatch,
            }
            print(f"{key}: n={len(r)} wr={wins.mean():.3f} pf={pos/neg:.2f} "
                  f"| independent check: {checked - mismatch}/{checked} match")

            if cfg_name == "VAL_FRESH" and tp_mult == 1.0:
                print("\n=== 6 Beispiel-Trades zum manuellen Nachpruefen (TP 1:1) ===")
                sample = tdf.sample(min(6, len(tdf)), random_state=7).sort_values("ts")
                for _, t in sample.iterrows():
                    d = daily[t["instrument"]]
                    ts = pd.Timestamp(t["ts"])
                    print(f"  {t['instrument']:7s} {t['side']:5s} Entry {ts.date()} "
                          f"@ {t['entry']:.5g} | SL {t['sl']:.5g} | TP {t['tp']:.5g} "
                          f"-> {t['reason']} ({t['r']:+.2f}R, {t['bars']} Tage)")
                print()

    with open(os.path.join(REPORT_DIR, "tp_sweep_verification.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("Saved tp_sweep_verification.json")


if __name__ == "__main__":
    main()
