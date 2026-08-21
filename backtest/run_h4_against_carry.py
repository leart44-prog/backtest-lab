"""4H test of the against-carry reversal config.

--source local : repo 4H bars (broker-aligned, 28 FX pairs, 2013-2026),
                 valuation on the 4H frame (as the indicator would show on
                 a 4H chart), futures legs daily. Era split at 2021-01-01.
--source dukas : Dukascopy 1H cache -> 4H (22:00-UTC aligned bins via
                 offset='2h'), 21 crosses, as far back as the cache
                 reaches (extension script downloads 2003+). Era split at
                 2013-01-01 (unseen decade).

Cells (declared): age {500, 3000} x TP {2.0, 2.5, 3.0, 4.0}, formations
DBR/RBD, fresh only, valuation gate, honest fills, costs. Carry split
AGAINST / WITH the higher-yielding currency via backtest/policy_rates.py.
"""
import argparse
import glob
import json
import lzma
import os
import struct
import sys

sys.path.insert(0, "/home/user/backtest-lab")
SCRATCH = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("DUKAS_CACHE", os.path.join(SCRATCH, "dukas"))
os.environ.setdefault("DUKAS_DAILY_CACHE", os.path.join(SCRATCH, "dukas_daily"))

import numpy as np
import pandas as pd

from backtest.course_sd import UNIVERSE, asset_class, run_course_sd, valuation_score
from backtest.v5_zones import scan_v5_zones
from backtest.data import load_bars, load_manifest
from backtest.policy_rates import rate_series

CROSSES = ("EURGBP EURJPY EURCHF EURAUD EURCAD EURNZD GBPJPY GBPCHF GBPAUD "
           "GBPCAD GBPNZD AUDJPY AUDCHF AUDCAD AUDNZD NZDJPY NZDCHF NZDCAD "
           "CADJPY CADCHF CHFJPY").split()
AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


def load_local(smoke=False):
    have = {m["name"] for m in load_manifest()}
    names = [u for u in UNIVERSE if u in have and asset_class(u).startswith("fx")]
    if smoke:
        names = names[:3]
    bars = {u: load_bars(u) for u in names}
    # valuation legs at NATIVE 4H resolution — exactly like the original 4H
    # study (run_course_sd.py) and like the v6 indicator on a 4H chart
    fut = {f: load_bars(f)["close"]
           for f in ("6E", "6B", "6A", "6N", "6C", "6S", "6J") if f in have}
    return bars, fut, pd.Timestamp("2021-01-01", tz="UTC")


MAJORS = "EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD".split()


def _load_dukas_4h(pair):
    scale = 1e3 if "JPY" in pair else 1e5
    rows = []
    for path in sorted(glob.glob(os.path.join(os.environ["DUKAS_CACHE"], pair, "*.bi5"))):
        y, m = os.path.basename(path)[:-4].split("-")
        raw = lzma.decompress(open(path, "rb").read())
        base = pd.Timestamp(year=int(y), month=int(m) + 1, day=1, tz="UTC")
        for k in range(len(raw) // 24):
            t, o, c, l, h, v = struct.unpack(">5if", raw[k * 24:(k + 1) * 24])
            if v == 0 and h == l:
                continue
            rows.append((base + pd.Timedelta(seconds=t), o / scale, h / scale,
                         l / scale, c / scale))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df = df.set_index("ts").sort_index()
    df = df[df.index.dayofweek <= 4]
    return df.resample("4h", offset="2h").agg(AGG).dropna()


def load_dukas(smoke=False):
    frames = {}
    for pair in (CROSSES[:3] if smoke else CROSSES):
        frames[pair] = _load_dukas_4h(pair)
        print(f"  {pair}: {len(frames[pair])} 4H bars "
              f"{frames[pair].index[0].date()} -> {frames[pair].index[-1].date()}",
              flush=True)
    # valuation legs at NATIVE 4H resolution from the Dukascopy majors
    leg = {"6E": ("EURUSD", False), "6B": ("GBPUSD", False), "6A": ("AUDUSD", False),
           "6N": ("NZDUSD", False), "6C": ("USDCAD", True), "6S": ("USDCHF", True),
           "6J": ("USDJPY", True)}
    fut = {}
    for code, (p, inv) in leg.items():
        s = _load_dukas_4h(p)["close"]
        if len(s) < 5000:
            raise SystemExit(f"missing 1H history for major {p} — run h4_dl.py first")
        fut[code] = (1.0 / s) if inv else s
    return frames, fut, pd.Timestamp("2013-01-01", tz="UTC")


def st(r):
    if len(r) == 0:
        return {"n": 0}
    w = r > 0
    pos, neg = r[w].sum(), -r[~w].sum()
    return {"n": int(len(r)), "wr": round(float(w.mean()), 3),
            "avgR": round(float(r.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("local", "dukas"), required=True)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    bars, fut, era_split = (load_local if args.source == "local" else load_dukas)(args.smoke)
    diffs = {u: rate_series(u[:3], bars[u].index) - rate_series(u[3:], bars[u].index)
             for u in bars}
    scores = {u: valuation_score(u, bars[u], fut, {}) for u in bars}
    # zones depend only on the bars: scan once per pair, deep-copy per cell
    # (the engine mutates zone state during a run)
    import copy
    zcache = {u: scan_v5_zones(bars[u]) for u in bars}
    print(f"loaded {len(bars)} pairs ({args.source}), "
          f"zones scanned: {sum(len(z) for z in zcache.values())}", flush=True)

    ages = (500,) if args.smoke else (500, 3000)
    tps = (3.0,) if args.smoke else (2.0, 2.5, 3.0, 4.0)
    results = {}
    for age in ages:
        for tp in tps:
            rows = []
            for u in bars:
                s, t1 = scores[u]
                zs = copy.deepcopy(zcache[u])
                for tr in run_course_sd(u, bars[u], s, t1, None, None,
                                        use_valuation=True, use_htf=False,
                                        fresh_mode="fresh_only",
                                        zone_scanner=lambda df, z=zs: z, target_r=tp,
                                        formations=(2, 3), max_zone_age=age):
                    d = diffs[u]
                    i = min(d.index.searchsorted(tr["ts"]), len(d) - 1)
                    lvl = float(d.iloc[i])
                    long = tr["side"] == "long"
                    tr["carry"] = ("against" if (long and lvl < 0) or (not long and lvl > 0)
                                   else "with" if lvl != 0 else "neutral")
                    rows.append(tr)
            t = pd.DataFrame(rows).sort_values("ts")
            key = f"{args.source}|age{age}|tp{tp}"
            early = t["ts"] < era_split
            cell = {}
            for grp, mask in (("ALL", np.ones(len(t), dtype=bool)),
                              ("AGAINST", (t["carry"] == "against").to_numpy()),
                              ("WITH", (t["carry"] == "with").to_numpy())):
                cell[grp] = {"all": st(t[mask]["r"].to_numpy()),
                             "early": st(t[mask & early.to_numpy()]["r"].to_numpy()),
                             "late": st(t[mask & ~early.to_numpy()]["r"].to_numpy())}
            results[key] = cell
            a, g = cell["ALL"]["all"], cell["AGAINST"]
            print(f"RESULT {key}: ALL n={a['n']} avgR={a.get('avgR')} pf={a.get('pf')} | "
                  f"AGAINST n={g['all']['n']} avgR={g['all'].get('avgR')} pf={g['all'].get('pf')} "
                  f"(early {g['early'].get('pf')}/n{g['early'].get('n')}, "
                  f"late {g['late'].get('pf')}/n{g['late'].get('n')}) | "
                  f"WITH pf={cell['WITH']['all'].get('pf')}", flush=True)

    out = os.path.join(SCRATCH, f"h4_results_{args.source}.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved {out}", flush=True)


if __name__ == "__main__":
    main()
