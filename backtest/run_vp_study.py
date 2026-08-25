"""Weekly/monthly volume-profile study (declared before running).

Universe: 28 FX (21 crosses + 7 USD majors), Dukascopy 1H with tick
volume, 2003-2026, daily execution, honest fills (limit at level,
same-bar stopout = -1R, SL-before-TP, EOS at close), costs, one position
per pair, era split 2013-01-01.

Family A - pure VP edges: limit LONG at the prior completed period's VAL
(only if the previous daily close was above it), limit SHORT at VAH
(prev close below), first touch per period+side, SL = 25% of the value-
area height beyond the level. TP variants: POC (mean reversion into the
VA), EDGE (opposite VA edge), 2.5R. Periods: W, M -> 6 cells, both
sides pooled (long/short also reported).

Family B - confluence: v5 S/D zone trades (fresh only, first touch, no
valuation, TP 2.5R, engine as everywhere) split by whether the zone's
proximal lies within 0.30 x VA height of the applicable W- or M-level
(demand near VAL, supply near VAH) vs the complement. 3 splits: W, M,
either.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest
from .course_sd import run_course_sd
from .v5_zones import scan_v5_zones
from .vp_levels import VPLevels, applicable, build_levels, load_dukas_1h

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "reports", "vp_study")
PAIRS = ("EURGBP EURJPY EURCHF EURAUD EURCAD EURNZD GBPJPY GBPCHF GBPAUD "
         "GBPCAD GBPNZD AUDJPY AUDCHF AUDCAD AUDNZD NZDJPY NZDCHF NZDCAD "
         "CADJPY CADCHF CHFJPY EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD "
         "NZDUSD").split()
AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}
STOP_FRAC = 0.25      # of VA height beyond the level
CONF_TOL = 0.30       # of VA height, zone-proximal to VP-level distance
SPLIT = pd.Timestamp("2013-01-01", tz="UTC")


def st(r):
    if len(r) == 0:
        return {"n": 0}
    r = np.asarray(r, dtype=float)
    w = r > 0
    pos, neg = r[w].sum(), -r[~w].sum()
    return {"n": int(len(r)), "wr": round(float(w.mean()), 3),
            "avgR": round(float(r.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None}


def sim_family_a(name, daily, levels, freq, tp_mode, cost):
    """Limit at VAL/VAH of the prior completed period; returns trade dicts."""
    friction = cost.spread_price + cost.slippage_price
    h = daily["high"].to_numpy()
    l = daily["low"].to_numpy()
    c = daily["close"].to_numpy()
    idx = daily.index
    n = len(daily)
    trades = []
    filled = set()            # (period_start, side)
    in_pos_until = -1
    for i in range(1, n):
        lv = applicable(idx[i], levels, freq)
        if lv is None or lv.va_h <= 0:
            continue
        for side in ("long", "short"):
            key = (lv.start, side)
            if key in filled or i <= in_pos_until:
                continue
            if side == "long":
                level, sl = lv.val, lv.val - STOP_FRAC * lv.va_h
                touched = l[i] <= level
                approach_ok = c[i - 1] > level
                tp_raw = {"POC": lv.poc, "EDGE": lv.vah}.get(tp_mode)
            else:
                level, sl = lv.vah, lv.vah + STOP_FRAC * lv.va_h
                touched = h[i] >= level
                approach_ok = c[i - 1] < level
                tp_raw = {"POC": lv.poc, "EDGE": lv.val}.get(tp_mode)
            if not (touched and approach_ok):
                continue
            filled.add(key)
            entry = level + (friction if side == "long" else -friction)
            risk = abs(entry - sl)
            if risk <= 0:
                continue
            if tp_mode == "R25":
                tp = entry + (2.5 * risk if side == "long" else -2.5 * risk)
            else:
                tp = tp_raw
                if (side == "long" and tp <= entry) or (side == "short" and tp >= entry):
                    continue
            comm_r = 2.0 * cost.commission_pct * entry / risk
            if (l[i] <= sl) if side == "long" else (h[i] >= sl):
                trades.append({"instrument": name, "ts": idx[i], "side": side,
                               "r": -1.0 - comm_r, "reason": "SAME_BAR_SL"})
                in_pos_until = i
                continue
            r_out, bars_held, reason = None, 0, "EOS"
            for j in range(i + 1, min(n, i + 400)):
                bars_held = j - i
                if (l[j] <= sl) if side == "long" else (h[j] >= sl):
                    r_out, reason = -1.0, "SL"
                    break
                if (h[j] >= tp) if side == "long" else (l[j] <= tp):
                    r_out = (tp - entry) / risk if side == "long" else (entry - tp) / risk
                    reason = "TP"
                    break
            if r_out is None:
                last = min(n - 1, i + 399)
                r_out = ((c[last] - entry) / risk) if side == "long" else ((entry - c[last]) / risk)
                bars_held = last - i
            trades.append({"instrument": name, "ts": idx[i], "side": side,
                           "r": float(r_out) - comm_r, "reason": reason})
            in_pos_until = i + max(bars_held, 1)
    return trades


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    meta = {m["name"]: m for m in load_manifest()}
    daily, lev_w, lev_m = {}, {}, {}
    for u in PAIRS:
        h1 = load_dukas_1h(u)
        if len(h1) < 5000:
            print(f"{u}: insufficient 1H data, skipped", flush=True)
            continue
        d = h1.resample("1D").agg(AGG).dropna()
        d = d[(d["high"] - d["low"]) > 0]
        daily[u] = d
        lev_w[u] = build_levels(h1, "W")
        lev_m[u] = build_levels(h1, "M")
        print(f"{u}: {len(d)} days, {len(lev_w[u])} weekly / {len(lev_m[u])} monthly profiles",
              flush=True)

    results = {}
    # ── Family A ─────────────────────────────────────────────────────
    for freq, levs in (("W", lev_w), ("M", lev_m)):
        for tp_mode in ("POC", "EDGE", "R25"):
            rows = []
            for u in daily:
                m = meta[u]
                cost = cost_for(u, m.get("jpy", False), m["type"], m["category"],
                                m.get("tick"))
                rows.extend(sim_family_a(u, daily[u], levs[u], freq, tp_mode, cost))
            t = pd.DataFrame(rows).sort_values("ts")
            early = t["ts"] < SPLIT
            key = f"A|{freq}|{tp_mode}"
            results[key] = {"all": st(t["r"]), "early": st(t[early]["r"]),
                            "late": st(t[~early]["r"]),
                            "long": st(t[t["side"] == "long"]["r"]),
                            "short": st(t[t["side"] == "short"]["r"])}
            a = results[key]
            print(f"RESULT {key}: {a['all']} | early {a['early'].get('pf')} "
                  f"late {a['late'].get('pf')} | L {a['long'].get('pf')} "
                  f"S {a['short'].get('pf')}", flush=True)

    # ── Family B ─────────────────────────────────────────────────────
    rows = []
    for u in daily:
        for tr in run_course_sd(u, daily[u], None, 0.0, None, None,
                                use_valuation=False, use_htf=False,
                                fresh_mode="fresh_only", zone_scanner=scan_v5_zones,
                                target_r=2.5, formations=(0, 1, 2, 3, 4)):
            conf = {}
            for freq, levs in (("W", lev_w[u]), ("M", lev_m[u])):
                lv = applicable(tr["ts"], levs, freq)
                ok = False
                if lv is not None and lv.va_h > 0:
                    lvl = lv.val if tr["side"] == "long" else lv.vah
                    ok = abs(tr["entry"] - lvl) <= CONF_TOL * lv.va_h
                conf[freq] = ok
            tr["conf_w"], tr["conf_m"] = conf["W"], conf["M"]
            rows.append(tr)
    t = pd.DataFrame(rows).sort_values("ts")
    early = t["ts"] < SPLIT
    for tag, mask in (("W", t["conf_w"]), ("M", t["conf_m"]),
                      ("either", t["conf_w"] | t["conf_m"])):
        m = mask.to_numpy()
        results[f"B|conf_{tag}"] = {"conf": st(t[m]["r"]),
                                    "conf_early": st(t[m & early.to_numpy()]["r"]),
                                    "conf_late": st(t[m & ~early.to_numpy()]["r"]),
                                    "no_conf": st(t[~m]["r"])}
        b = results[f"B|conf_{tag}"]
        print(f"RESULT B|{tag}: conf {b['conf']} (early {b['conf_early'].get('pf')} "
              f"late {b['conf_late'].get('pf')}) vs no-conf pf={b['no_conf'].get('pf')} "
              f"n={b['no_conf'].get('n')}", flush=True)

    with open(os.path.join(REPORT_DIR, "vp_study_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Saved vp_study_results.json", flush=True)


if __name__ == "__main__":
    main()
