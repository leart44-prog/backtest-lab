"""Independent 1H validation of the mentor-study replication on Dukascopy data.

1. Download BID 1H candles for the 21 crosses, Jan 2016 - Feb 2026 (cached).
2. Aggregate to daily (Mon-Fri, no-range days dropped, matching the study's
   data cleaning), run the mentor protocol (MENTOR_CFG) on the DUKASCOPY
   daily candles -> fills.
3. Evaluate:
   a) mentor daily-ledger convention (same-bar TP counts, Loss first)
   b) full 1H resolution: conservative (touch hour: only SL counts) and
      optimistic (touch hour: TP counts) -> the truth band
   c) reclassify the daily same-bar "wins" on 1H sequencing
   for both targets (1:1 and 1:2).
"""
import json
import lzma
import os
import struct
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from backtest.otc_v3_zones import MENTOR_CFG, collect_fills, STOP_PCT  # noqa: E402

SCRATCH = os.environ.get("DUKAS_OUT", os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get("DUKAS_CACHE", os.path.join(SCRATCH, "dukas_cache"))
PAIRS = ("EURGBP EURJPY EURCHF EURAUD EURCAD EURNZD GBPJPY GBPCHF GBPAUD "
         "GBPCAD GBPNZD AUDJPY AUDCHF AUDCAD AUDNZD NZDJPY NZDCHF NZDCAD "
         "CADJPY CADCHF CHFJPY").split()
MONTHS = [(y, m) for y in range(2016, 2027) for m in range(12)
          if (y, m) <= (2026, 1)][:]          # 0-based months Jan16..Feb26
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(pair: str, y: int, m: int) -> str | None:
    path = os.path.join(CACHE, pair, f"{y}-{m:02d}.bi5")
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = f"https://datafeed.dukascopy.com/datafeed/{pair}/{y}/{m:02d}/BID_candles_hour_1.bi5"
    for attempt in range(6):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200 and r.content[:1] == b"\x5d":   # LZMA magic
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def load_pair(pair: str) -> pd.DataFrame:
    scale = 1e3 if "JPY" in pair else 1e5
    rows = []
    for y, m in MONTHS:
        path = os.path.join(CACHE, pair, f"{y}-{m:02d}.bi5")
        if not os.path.exists(path):
            continue
        raw = lzma.decompress(open(path, "rb").read())
        base = pd.Timestamp(year=y, month=m + 1, day=1, tz="UTC")
        for k in range(len(raw) // 24):
            t, o, c, l, h, v = struct.unpack(">5if", raw[k * 24:(k + 1) * 24])
            if v == 0 and h == l:                      # flat weekend/holiday filler
                continue
            rows.append((base + pd.Timedelta(seconds=t), o / scale, h / scale,
                         l / scale, c / scale))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df = df.set_index("ts").sort_index()
    return df


def main():
    # ── download (cached) ────────────────────────────────────────────
    jobs = [(p, y, m) for p in PAIRS for y, m in MONTHS]
    done = 0
    with ThreadPoolExecutor(8) as ex:
        for _ in ex.map(lambda j: fetch(*j), jobs):
            done += 1
            if done % 250 == 0:
                print(f"download {done}/{len(jobs)}", flush=True)

    # ── validation ───────────────────────────────────────────────────
    out = {}
    for target_tag, tr in (("1:1", 1.0), ("1:2", 2.0)):
        led = []            # mentor daily ledger results (1 win, 0 loss)
        cons, opti = [], []  # 1H-resolved results
        sbwin = dict(win=0, loss=0, unresolved=0)
        n_pairs = 0
        for pair in PAIRS:
            h1 = load_pair(pair)
            if len(h1) < 5000:
                print(f"{pair}: only {len(h1)} 1H bars, skipping", flush=True)
                continue
            n_pairs += 1
            h1 = h1[h1.index.dayofweek <= 4]
            agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
            d = h1.resample("1D").agg(agg).dropna()
            d = d[(d["high"] - d["low"]) > 0]
            d = d[d.index >= d.index[-1] - pd.DateOffset(years=10)]
            h1 = h1[h1.index >= d.index[0]]
            H1h, L1h = h1["high"].to_numpy(), h1["low"].to_numpy()
            days1h = h1.index.normalize()
            Hd, Ld = d["high"].to_numpy(), d["low"].to_numpy()
            fills = collect_fills(d, cfg=MENTOR_CFG)
            for f in fills:
                i, dem = f["i"], f["is_demand"]
                hgt = abs(f["prox_p"] - f["distal"])
                if hgt <= 0:
                    continue
                entry = f["prox_p"]
                sl = f["distal"] - STOP_PCT * hgt if dem else f["distal"] + STOP_PCT * hgt
                risk = abs(entry - sl)
                tp = entry + tr * risk if dem else entry - tr * risk
                # a) mentor daily ledger from fill bar
                r_led = None
                for j in range(i, len(d)):
                    if (Ld[j] <= sl) if dem else (Hd[j] >= sl):
                        r_led = 0
                        break
                    if (Hd[j] >= tp) if dem else (Ld[j] <= tp):
                        r_led = 1
                        break
                if r_led is not None:
                    led.append(r_led)
                # b) 1H resolution from the first touching hour
                k0 = int(np.searchsorted(days1h, d.index[i]))
                kf = None
                for k in range(k0, len(h1)):
                    if (L1h[k] <= entry) if dem else (H1h[k] >= entry):
                        kf = k
                        break
                if kf is None:
                    continue

                def resolve(incl_tp_touch_bar):
                    slh = (L1h[kf] <= sl) if dem else (H1h[kf] >= sl)
                    tph = (H1h[kf] >= tp) if dem else (L1h[kf] <= tp)
                    if slh:
                        return 0
                    if incl_tp_touch_bar and tph:
                        return 1
                    for k in range(kf + 1, len(h1)):
                        if (L1h[k] <= sl) if dem else (H1h[k] >= sl):
                            return 0
                        if (H1h[k] >= tp) if dem else (L1h[k] <= tp):
                            return 1
                    return None
                rc, ro = resolve(False), resolve(True)
                if rc is not None:
                    cons.append(rc)
                if ro is not None:
                    opti.append(ro)
                # c) daily same-bar "win" reclassification
                sl_d = (Ld[i] <= sl) if dem else (Hd[i] >= sl)
                tp_d = (Hd[i] >= tp) if dem else (Ld[i] <= tp)
                if tp_d and not sl_d:
                    if rc == 1:
                        sbwin["win"] += 1
                    elif rc == 0:
                        sbwin["loss"] += 1
                    else:
                        sbwin["unresolved"] += 1
        led, cons, opti = map(np.array, (led, cons, opti))
        need = 0.5 if tr == 1.0 else 1 / 3
        res = {"pairs": n_pairs,
               "daily_ledger": {"n": len(led), "wr": round(float(led.mean()), 3)},
               "h1_conservative": {"n": len(cons), "wr": round(float(cons.mean()), 3)},
               "h1_optimistic": {"n": len(opti), "wr": round(float(opti.mean()), 3)},
               "breakeven_needs": round(need, 3),
               "daily_samebar_wins_on_1h": dict(sbwin)}
        out[target_tag] = res
        print(f"\nTarget {target_tag} ({n_pairs} pairs):", flush=True)
        print(f"  Mentor-Ledger (Daily):   n={len(led)}  wr={led.mean()*100:.1f}%")
        print(f"  1H konservativ:          n={len(cons)} wr={cons.mean()*100:.1f}%")
        print(f"  1H optimistisch:         n={len(opti)} wr={opti.mean()*100:.1f}%")
        print(f"  Breakeven noetig:        {need*100:.1f}%")
        sb = sbwin
        tot = sb["win"] + sb["loss"] + sb["unresolved"]
        if tot:
            print(f"  Daily-Same-bar-Wins auf 1H: {tot} -> echt {sb['win']} "
                  f"({sb['win']/tot*100:.1f}%), Verlierer {sb['loss']} "
                  f"({sb['loss']/tot*100:.1f}%)")

    with open(os.path.join(SCRATCH, "dukas_validation.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("\nSaved dukas_validation.json", flush=True)


if __name__ == "__main__":
    main()
