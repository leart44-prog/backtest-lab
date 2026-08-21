"""Fed policy phases vs raw chart behaviour (FX + US indices) and vs the
zone-reversal config, 2003-2026.

Phases from the documented Fed funds history (dates are public record):
hiking / cutting / hold-low / hold-high. For each phase:
  - FX (28 Dukascopy pairs): mean absolute net move, mean trend-efficiency
    (|net| / path length -- 0 = pure range, 1 = straight line), ann. vol
  - US indices (Dukascopy CFDs, scale-invariant metrics): net move, max DD
  - the config's trades (REVERSALS age100 and age500 on Dukascopy FX):
    n, avg R, PF per phase.
"""
import json
import lzma
import os
import struct

import numpy as np
import pandas as pd

os.environ.setdefault("DUKAS_DAILY_CACHE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "dukas_daily"))
from backtest.validate_oos_dukascopy import (CROSSES, MAJORS, YEARS, fetch,   # noqa: E402
                                             load_daily)
from backtest.course_sd import run_course_sd, valuation_score                 # noqa: E402
from backtest.v5_zones import scan_v5_zones                                   # noqa: E402

SCRATCH = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ["DUKAS_DAILY_CACHE"]

PHASES = [
    ("2003-01-01", "2004-06-30", "hold_low",  "Hold tief 1.00-1.25%"),
    ("2004-06-30", "2006-06-29", "hiking",    "Anhebung 1.00->5.25%"),
    ("2006-06-29", "2007-09-18", "hold_high", "Hold hoch 5.25%"),
    ("2007-09-18", "2008-12-16", "cutting",   "Senkung 5.25->0.25% (GFC)"),
    ("2008-12-16", "2015-12-16", "hold_low",  "ZIRP + QE 0-0.25%"),
    ("2015-12-16", "2018-12-19", "hiking",    "Anhebung 0.25->2.50%"),
    ("2018-12-19", "2019-07-31", "hold_high", "Hold 2.25-2.50%"),
    ("2019-07-31", "2020-03-15", "cutting",   "Senkung + Covid-Schock"),
    ("2020-03-15", "2022-03-16", "hold_low",  "ZIRP + QE (Covid)"),
    ("2022-03-16", "2023-07-26", "hiking",    "Anhebung 0.25->5.50%"),
    ("2023-07-26", "2024-09-18", "hold_high", "Hold hoch 5.25-5.50%"),
    ("2024-09-18", "2026-02-27", "cutting",   "Senkungszyklus ab Sep 24"),
]

INDICES = ["USA500IDXUSD", "USATECHIDXUSD", "USA30IDXUSD", "USSC2000IDXUSD"]


def load_raw(pair):
    """Index CFDs: decode without price scale (metrics are scale-invariant)."""
    rows = []
    for y in YEARS:
        path = os.path.join(CACHE, pair, f"{y}.bi5")
        if not os.path.exists(path):
            continue
        raw = lzma.decompress(open(path, "rb").read())
        base = pd.Timestamp(year=y, month=1, day=1, tz="UTC")
        for k in range(len(raw) // 24):
            t, o, c, l, h, v = struct.unpack(">5if", raw[k * 24:(k + 1) * 24])
            if h == l:
                continue
            rows.append((base + pd.Timedelta(seconds=t), float(o), float(h),
                         float(l), float(c)))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df = df.set_index("ts").sort_index()
    return df[df.index.dayofweek <= 4]


def phase_metrics(close: pd.Series, a, b):
    s = close[(close.index >= a) & (close.index < b)]
    if len(s) < 40:
        return None
    net = abs(s.iloc[-1] / s.iloc[0] - 1.0)
    path = float(np.abs(np.diff(np.log(s.to_numpy()))).sum())
    eff = abs(float(np.log(s.iloc[-1] / s.iloc[0]))) / path if path > 0 else 0.0
    vol = float(pd.Series(np.diff(np.log(s.to_numpy()))).std() * np.sqrt(252))
    roll = s / s.cummax() - 1.0
    return {"net_pct": round(net * 100, 1), "eff": round(eff, 3),
            "vol": round(vol * 100, 1), "maxdd_pct": round(float(roll.min()) * 100, 1)}


def main():
    # index CFD download (year files, cached, retries handle the 503s)
    for sym in INDICES:
        for y in YEARS:
            fetch(sym, y)
    idx = {}
    for sym in INDICES:
        d = load_raw(sym)
        if len(d) > 300:
            idx[sym] = d
        print(f"{sym}: {len(d)} days "
              f"{d.index[0].date() if len(d) else '-'} -> "
              f"{d.index[-1].date() if len(d) else '-'}", flush=True)

    daily = {p: load_daily(p) for p in CROSSES + MAJORS}
    daily = {p: d for p, d in daily.items() if len(d) > 500}

    # config trades (REVERSALS age100 / age500) on Dukascopy FX
    leg = {"6E": ("EURUSD", False), "6B": ("GBPUSD", False), "6A": ("AUDUSD", False),
           "6N": ("NZDUSD", False), "6C": ("USDCAD", True), "6S": ("USDCHF", True),
           "6J": ("USDJPY", True)}
    fut = {c: (1.0 / daily[p]["close"] if inv else daily[p]["close"])
           for c, (p, inv) in leg.items()}
    trades = {}
    for age in (100, 500):
        rows = []
        for u in daily:
            s, t1 = valuation_score(u, daily[u], fut, {})
            rows.extend(run_course_sd(u, daily[u], s, t1, None, None,
                                      use_valuation=True, use_htf=False,
                                      fresh_mode="fresh_only",
                                      zone_scanner=scan_v5_zones, target_r=2.5,
                                      formations=(2, 3), max_zone_age=age))
        trades[age] = pd.DataFrame(rows).sort_values("ts")

    out = []
    for a_s, b_s, kind, label in PHASES:
        a = pd.Timestamp(a_s, tz="UTC")
        b = pd.Timestamp(b_s, tz="UTC")
        fx = [m for p in daily
              if (m := phase_metrics(daily[p]["close"], a, b)) is not None]
        row = {"phase": label, "kind": kind, "from": a_s, "to": b_s,
               "fx_pairs": len(fx),
               "fx_eff_mean": round(float(np.mean([m["eff"] for m in fx])), 3) if fx else None,
               "fx_net_mean_pct": round(float(np.mean([m["net_pct"] for m in fx])), 1) if fx else None,
               "fx_vol_mean_pct": round(float(np.mean([m["vol"] for m in fx])), 1) if fx else None}
        spx = phase_metrics(idx["USA500IDXUSD"]["close"], a, b) if "USA500IDXUSD" in idx else None
        row["spx"] = spx
        for age in (100, 500):
            t = trades[age]
            sel = t[(t["ts"] >= a) & (t["ts"] < b)]["r"].to_numpy()
            if len(sel):
                w = sel > 0
                pos, neg = sel[w].sum(), -sel[~w].sum()
                row[f"cfg{age}"] = {"n": int(len(sel)),
                                    "avg_r": round(float(sel.mean()), 3),
                                    "pf": round(float(pos / neg), 2) if neg > 0 else None}
            else:
                row[f"cfg{age}"] = {"n": 0}
        out.append(row)
        c1, c5 = row["cfg100"], row["cfg500"]
        print(f"{a_s[:7]}..{b_s[:7]} {kind:9s} | FX eff={row['fx_eff_mean']} "
              f"net={row['fx_net_mean_pct']}% vol={row['fx_vol_mean_pct']}% | "
              f"SPX {spx['net_pct'] if spx else '-'}% dd {spx['maxdd_pct'] if spx else '-'}% | "
              f"cfg100 n={c1['n']} avgR={c1.get('avg_r')} pf={c1.get('pf')} | "
              f"cfg500 n={c5['n']} avgR={c5.get('avg_r')} pf={c5.get('pf')}", flush=True)

    # aggregate by phase kind
    print("\n== Aggregat nach Phasentyp (cfg500) ==", flush=True)
    for kind in ("hold_low", "hold_high", "hiking", "cutting"):
        rs = []
        for a_s, b_s, k, _ in PHASES:
            if k != kind:
                continue
            a, b = pd.Timestamp(a_s, tz="UTC"), pd.Timestamp(b_s, tz="UTC")
            t = trades[500]
            rs.append(t[(t["ts"] >= a) & (t["ts"] < b)]["r"].to_numpy())
        r = np.concatenate(rs) if rs else np.array([])
        if len(r):
            w = r > 0
            pos, neg = r[w].sum(), -r[~w].sum()
            print(f"  {kind:9s}: n={len(r)} avgR={r.mean():+.3f} "
                  f"pf={pos/neg:.2f}" if neg > 0 else f"  {kind}: n={len(r)} all wins",
                  flush=True)

    with open(os.path.join(SCRATCH, "regime_phases.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("Saved regime_phases.json", flush=True)


if __name__ == "__main__":
    main()
