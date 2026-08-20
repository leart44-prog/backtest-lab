"""Out-of-sample validation of the best config on Dukascopy DAILY data.

Independent data source (Dukascopy BID daily, 2003-2026) AND an unseen
period (2003-2012 predates every dataset used in this repo). 28 FX
instruments: the 21 crosses + 7 USD majors. Valuation is built exactly
like the indicator's FX definition, from Dukascopy USD legs (XXX/USD
orientation; futures legs replaced by spot legs - documented deviation,
ROC-z-score is insensitive to the basis).

Cells (declared): {VAL_FRESH all formations, REVERSALS (DBR/RBD)} x
zone age {60, 100, 500}, v5 zones, fresh only, TP 2.5R, SL 25% beyond
distal, honest fills, costs. Reported split: UNSEEN (< 2013) vs OVERLAP
(>= 2013), plus pooled.
"""
import json
import lzma
import os
import struct
import time

import numpy as np
import pandas as pd
import requests

from backtest.course_sd import run_course_sd, valuation_score      # noqa: E402
from backtest.v5_zones import scan_v5_zones                        # noqa: E402

SCRATCH = os.environ.get("DUKAS_OUT", os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get("DUKAS_DAILY_CACHE", os.path.join(SCRATCH, "dukas_daily_cache"))
CROSSES = ("EURGBP EURJPY EURCHF EURAUD EURCAD EURNZD GBPJPY GBPCHF GBPAUD "
           "GBPCAD GBPNZD AUDJPY AUDCHF AUDCAD AUDNZD NZDJPY NZDCHF NZDCAD "
           "CADJPY CADCHF CHFJPY").split()
MAJORS = "EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD".split()
YEARS = list(range(2003, 2027))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(pair, y):
    path = os.path.join(CACHE, pair, f"{y}.bi5")
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = f"https://datafeed.dukascopy.com/datafeed/{pair}/{y}/BID_candles_day_1.bi5"
    for attempt in range(6):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200 and r.content[:1] == b"\x5d":
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def load_daily(pair):
    scale = 1e3 if "JPY" in pair else 1e5
    rows = []
    for y in YEARS:
        path = os.path.join(CACHE, pair, f"{y}.bi5")
        if not os.path.exists(path):
            continue
        raw = lzma.decompress(open(path, "rb").read())
        base = pd.Timestamp(year=y, month=1, day=1, tz="UTC")
        for k in range(len(raw) // 24):
            t, o, c, l, h, v = struct.unpack(">5if", raw[k * 24:(k + 1) * 24])
            if (v == 0 and h == l) or h == l:      # weekend/holiday filler
                continue
            rows.append((base + pd.Timedelta(seconds=t), o / scale, h / scale,
                         l / scale, c / scale))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df = df.set_index("ts").sort_index()
    return df[df.index.dayofweek <= 4]


def stats(r):
    if len(r) == 0:
        return {"n": 0}
    w = r > 0
    pos, neg = r[w].sum(), -r[~w].sum()
    return {"n": int(len(r)), "wr": round(float(w.mean()), 3),
            "pf": round(float(pos / neg), 2) if neg > 0 else None,
            "avg_r": round(float(r.mean()), 3), "sum_r": round(float(r.sum()), 1)}


def main():
    jobs = [(p, y) for p in CROSSES + MAJORS for y in YEARS]
    for k, (p, y) in enumerate(jobs):
        fetch(p, y)
        if (k + 1) % 100 == 0:
            print(f"download {k+1}/{len(jobs)}", flush=True)

    daily = {}
    for p in CROSSES + MAJORS:
        d = load_daily(p)
        if len(d) > 500:
            daily[p] = d
        print(f"{p}: {len(d)} days {d.index[0].date() if len(d) else '-'} -> "
              f"{d.index[-1].date() if len(d) else '-'}", flush=True)

    # valuation legs in futures orientation (XXX/USD), spot-built
    fut = {}
    leg = {"6E": ("EURUSD", False), "6B": ("GBPUSD", False), "6A": ("AUDUSD", False),
           "6N": ("NZDUSD", False), "6C": ("USDCAD", True), "6S": ("USDCHF", True),
           "6J": ("USDJPY", True)}
    for code, (pair, invert) in leg.items():
        s = daily[pair]["close"]
        fut[code] = (1.0 / s) if invert else s

    names = [p for p in CROSSES + MAJORS if p in daily]
    scores, t1s = {}, {}
    for u in names:
        s, t1 = valuation_score(u, daily[u], fut, {})
        scores[u] = s
        t1s[u] = t1

    unseen_end = pd.Timestamp("2013-01-01", tz="UTC")
    base = dict(use_valuation=True, use_htf=False, fresh_mode="fresh_only",
                zone_scanner=scan_v5_zones, target_r=2.5)
    CELLS = {}
    for age in (60, 100, 500):
        CELLS[f"VAL_FRESH|age{age}"] = dict(formations=(0, 1, 2, 3, 4), max_zone_age=age)
        CELLS[f"REVERSALS|age{age}"] = dict(formations=(2, 3), max_zone_age=age)

    results = {}
    for cname, extra in CELLS.items():
        kw = dict(base)
        kw.update(extra)
        rows = []
        for u in names:
            rows.extend(run_course_sd(u, daily[u], scores[u], t1s[u],
                                      None, None, **kw))
        tdf = pd.DataFrame(rows)
        if tdf.empty:
            results[cname] = {"all": {"n": 0}}
            continue
        tdf = tdf.sort_values("ts")
        res = {"all": stats(tdf["r"].to_numpy()),
               "UNSEEN_2003_2012": stats(tdf[tdf["ts"] < unseen_end]["r"].to_numpy()),
               "OVERLAP_2013_2026": stats(tdf[tdf["ts"] >= unseen_end]["r"].to_numpy())}
        results[cname] = res
        a, un, ov = res["all"], res["UNSEEN_2003_2012"], res["OVERLAP_2013_2026"]
        print(f"{cname}: all n={a['n']} pf={a.get('pf')} avgR={a.get('avg_r')} | "
              f"UNSEEN n={un.get('n')} pf={un.get('pf')} avgR={un.get('avg_r')} | "
              f"OVERLAP n={ov.get('n')} pf={ov.get('pf')} avgR={ov.get('avg_r')}", flush=True)

    with open(os.path.join(SCRATCH, "dukas_oos_validation.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Saved dukas_oos_validation.json", flush=True)


if __name__ == "__main__":
    main()
