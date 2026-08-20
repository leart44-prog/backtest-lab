"""Python port of the user's Pine v5 "OTC S&D Zoning v3" indicator.

Chart layer only (HTF1/HTF2 = off on the user's chart), daily bars.
Settings frozen to the user's chart screenshots (2026-08-20) — deviations
from the script defaults are marked (*):

  Candle anatomy   leg-in >40% body, base <=40%, leg-out >65% (defaults)
  Base             max 8 candles, leg-in-first (mode B), absorb small
                   decisive candles (N=1.0), stick-out >=50% of leg-out
                   range, max zone height 1.25x leg-out range (defaults)
  Detection extras 2-candle leg-out ON(*), min leg-out size off, avg range
                   lookback 10, leg-in wick into distal: explosive only,
                   departure gap ON, leg-in gap ON, pivot integration ON
                   (max 1.0x avg range, pivot length 5), overlap: SKIP if
                   overlapping active(*), speed-bump filter ON(*)
  Zone             proximal = PREFERRED(*) (base body extreme), skip 2
                   candles after leg-out before a test counts, max 200
                   zones kept (eviction oldest-first)
  Mitigation       close beyond distal
  Qualifiers       tradeable while tests < 1 (first-touch protocol);
                   coverage / action matrix / dep / pm / pivot gates off
  Trade plan       stop = 33.33% of zone height beyond distal(*)

Pine-fidelity notes:
  - Everything runs on confirmed bars; the per-bar order matches the
    script's main flow: pivot confirm -> pivot refresh (may extend active
    zones' distal) -> detection (incl. pivInit at creation) -> zone update
    (tests/fill -> mitigation -> arming).
  - Fill = Test invariant: a touch counts (and fills) only when armedPrev
    is set, i.e. earliest on the 3rd bar after the creation bar
    (skipBars=2). Creation bar is never countable.
  - tests increment only on the touch transition (inZone tracking), first
    test = the one virtual fill per zone. Mitigation runs AFTER the test
    on the same bar, so a bar can fill and mitigate.
  - Pivot integration: a confirmed swing pivot of the zone's kind lying
    beyond the distal within 1.0x avg range (creation-time normalizer,
    fallback zone height) pulls the distal to the pivot — at creation
    (against the 3 stored pivots, newest first) and retroactively when a
    pivot confirms later. Fills AFTER an extension use the extended
    distal for their SL; already-filled trades keep the frozen SL (here:
    the distal is snapshotted at fill time).

Two evaluation conventions on the identical fill stream:
  - eval_strict: the repo's honest-fill framework (spread/slippage in the
    entry, commission in R, same-bar stopout = -1R, entry-bar favorable
    follow-through ignored, SL-before-TP intrabar, one position per
    instrument) — directly comparable with every previous study.
  - eval_ledger: replication of the indicator's on-chart virtual ledger
    (fill at the raw proximal, resolution starts ON the fill bar so a
    same-bar TP counts, "Loss first" only when SL and TP hit in one bar,
    costR = 0, no position constraint) — approximates the chart table.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest

# ── user settings (see docstring) ────────────────────────────────────
LEG_IN_BP = 40.0     # effective = max(legIn, base) = 40
BASE_BP = 40.0
LEG_OUT_BP = 65.0
MAX_BASE = 8
SMALL_MULT = 1.0
STICK_PCT = 50.0
MAX_ZONE_X = 1.25
AVG_LEN = 10
PIV_LEN = 5
PIV_EXT_X = 1.0
SKIP_BARS = 2
MAX_ZONES = 200
STOP_PCT = 0.3333    # 33.33% of zone height beyond distal


@dataclass
class OZone:
    is_demand: bool
    fcode: int              # 1 RBR, 2 DBR, 3 RBD, 4 DBD
    prox_w: float
    prox_p: float
    distal: float
    created_i: int
    avg_r: float
    gap: bool               # any gap integrated (info)
    tests: int = 0
    in_zone: bool = False
    armed_prev: bool = False
    mitigated: bool = False


def _bp(o, h, l, c, k) -> float:
    r = h[k] - l[k]
    return abs(c[k] - o[k]) / r * 100.0 if r > 0 else 0.0


def _piv_integrate(z: OZone, piv: float) -> None:
    norm0 = z.avg_r if (z.avg_r and not np.isnan(z.avg_r)) else abs(z.prox_w - z.distal)
    beyond = (z.distal - piv) if z.is_demand else (piv - z.distal)
    if beyond > 0 and norm0 > 0 and beyond / norm0 <= PIV_EXT_X:
        z.distal = piv


def _detect_at(o, h, l, c, i: int, s: int):
    """V3 chain for leg-out offset s (1 = single candle i, 2 = candles
    i-1..i combined). Returns a zone-candidate dict or None. Mirrors
    f_detectAt(); overlap handling happens in the caller."""
    if i + 1 < s + MAX_BASE + AVG_LEN + 1:
        return None
    lo_o = o[i - 1] if s == 2 else o[i]
    lo_c = c[i]
    lo_h = max(h[i], h[i - 1]) if s == 2 else h[i]
    lo_l = min(l[i], l[i - 1]) if s == 2 else l[i]
    lo_r = lo_h - lo_l
    lo_bp = abs(lo_c - lo_o) / lo_r * 100.0 if lo_r > 0 else 0.0
    bull = lo_c > lo_o
    bear = lo_c < lo_o
    if not ((bull or bear) and lo_bp > LEG_OUT_BP):
        return None
    avg_range = float(np.mean([h[i - k] - l[i - k] for k in range(s, s + AVG_LEN)]))

    # mode B: nearest decisive leg-in whose base is consistent
    leg_in_off = 0
    b_len = 0
    found = False
    avg_b = None
    for j in range(s + 1, s + MAX_BASE + 1):
        if i - j < 0:
            break
        if _bp(o, h, l, c, i - j) > LEG_IN_BP:            # decisive candidate
            ci, si = 0, 0.0
            for k in range(s, j):
                if _bp(o, h, l, c, i - k) <= BASE_BP:
                    ci += 1
                    si += h[i - k] - l[i - k]
            ab = si / ci if ci > 0 else None
            any_bad = False
            for k in range(s, j):
                if _bp(o, h, l, c, i - k) > BASE_BP:      # not indecisive
                    absorbable = (_bp(o, h, l, c, i - k) > LEG_IN_BP and ci >= 1
                                  and ab is not None
                                  and (h[i - k] - l[i - k]) <= SMALL_MULT * ab)
                    if not absorbable:
                        any_bad = True
            if not any_bad:
                j_abs = (ci >= 1 and ab is not None
                         and (h[i - j] - l[i - j]) <= SMALL_MULT * ab)
                if not j_abs:
                    leg_in_off = j
                    b_len = j - s
                    avg_b = ab
                    found = True
                    break
    if not found:
        return None

    # 2-candle leg-out: neither candle may be small vs the base average
    if s == 2 and avg_b is not None:
        if (h[i] - l[i]) <= SMALL_MULT * avg_b or (h[i - 1] - l[i - 1]) <= SMALL_MULT * avg_b:
            return None

    b_high = max(h[i - k] for k in range(s, s + b_len))
    b_low = min(l[i - k] for k in range(s, s + b_len))
    b_body_hi = max(max(o[i - k], c[i - k]) for k in range(s, s + b_len))
    b_body_lo = min(min(o[i - k], c[i - k]) for k in range(s, s + b_len))

    is_dem = bull
    li = i - leg_in_off
    leg_in_bull = c[li] > o[li]
    fcode = (1 if leg_in_bull else 2) if is_dem else (3 if leg_in_bull else 4)
    reversal = fcode in (2, 3)

    prox_w = b_high if is_dem else b_low
    prox_p = b_body_hi if is_dem else b_body_lo
    distal = min(b_low, lo_l) if is_dem else max(b_high, lo_h)
    bounds_ok = (prox_p > distal and prox_w > distal) if is_dem else \
                (prox_p < distal and prox_w < distal)
    if not bounds_ok:
        return None
    zh = abs(prox_w - distal)

    # leg-in wick extension (reversals, explosive leg-in only) — after checks
    li_expl = _bp(o, h, l, c, li) > LEG_OUT_BP
    distal_x = distal
    if reversal and li_expl:
        distal_x = min(distal, l[li]) if is_dem else max(distal, h[li])

    # gap integration (departure gap, then leg-in gap) — after checks
    prox_wx, prox_px = prox_w, prox_p
    gap = False
    if is_dem and lo_l > b_high:                 # leg-out gapped up past the base
        gap = True
        prox_wx = min(lo_o, lo_c)
        prox_px = lo_l
    if (not is_dem) and lo_h < b_low:            # leg-out gapped down past the base
        gap = True
        prox_wx = max(lo_o, lo_c)
        prox_px = lo_h
    li_h, li_l = h[li], l[li]
    li_body_hi = max(o[li], c[li])
    li_body_lo = min(o[li], c[li])
    if li_l > b_high:                            # leg-in entirely above the base
        gap = True
        if is_dem:
            prox_wx = max(prox_wx, li_body_lo)
            prox_px = max(prox_px, li_l)
        else:
            distal_x = max(distal_x, li_l)
    if li_h < b_low:                             # leg-in entirely below the base
        gap = True
        if is_dem:
            distal_x = min(distal_x, li_h)
        else:
            prox_wx = min(prox_wx, li_body_hi)
            prox_px = min(prox_px, li_h)

    over = (lo_h - b_high) if is_dem else (b_low - lo_l)
    if not (lo_r > 0 and over / lo_r * 100.0 >= STICK_PCT):
        return None
    if not (zh <= MAX_ZONE_X * lo_r):
        return None
    # speed bump: 1-candle base, same-colour explosive leg-in (continuation pause)
    if b_len == 1 and leg_in_bull == bull and li_expl:
        return None

    return {"is_demand": is_dem, "fcode": fcode, "prox_w": prox_wx,
            "prox_p": prox_px, "distal": distal_x, "avg_r": avg_range,
            "gap": gap}


def _create(zones: list[OZone], d: dict, i: int,
            piv_h: list[float], piv_l: list[float]) -> OZone | None:
    """Overlap mode 'Skip if overlapping active': drop the candidate if it
    overlaps an ACTIVE same-side zone. Then pivInit against the 3 stored
    pivots of the zone's kind (newest first) — may extend the distal."""
    lo = min(d["prox_w"], d["distal"])
    hi = max(d["prox_w"], d["distal"])
    for zz in zones:
        if zz.is_demand == d["is_demand"] and not zz.mitigated:
            zlo = min(zz.prox_w, zz.distal)
            zhi = max(zz.prox_w, zz.distal)
            if hi >= zlo and zhi >= lo:
                return None
    z = OZone(d["is_demand"], d["fcode"], d["prox_w"], d["prox_p"],
              d["distal"], i, d["avg_r"], d["gap"])
    for piv in (piv_l if z.is_demand else piv_h):
        _piv_integrate(z, piv)
    zones.append(z)
    while len(zones) > MAX_ZONES:
        zones.pop(0)
    return z


def collect_fills(df: pd.DataFrame) -> list[dict]:
    """Run the full per-bar state machine; return the first-test fill
    events: {i, is_demand, fcode, prox_p, distal (frozen at fill), gap}."""
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    zones: list[OZone] = []
    piv_h: list[float] = []
    piv_l: list[float] = []
    fills: list[dict] = []
    zone_on_prev = False

    for i in range(n):
        # 1. pivot confirm at offset PIV_LEN (strict newer side, ties on older)
        new_ph, new_pl = None, None
        if i >= 2 * PIV_LEN:
            p = i - PIV_LEN
            hp, lp = h[p], l[p]
            if hp > h[p + 1:i + 1].max() and hp >= h[i - 2 * PIV_LEN:p].max():
                new_ph = hp
            if lp < l[p + 1:i + 1].min() and lp <= l[i - 2 * PIV_LEN:p].min():
                new_pl = lp
            if new_ph is not None:
                piv_h.insert(0, new_ph)
                del piv_h[3:]
            if new_pl is not None:
                piv_l.insert(0, new_pl)
                del piv_l[3:]
            if new_ph is not None or new_pl is not None:
                for z in zones:
                    if not z.mitigated:
                        piv = new_pl if z.is_demand else new_ph
                        if piv is not None:
                            _piv_integrate(z, piv)

        # 2. detection: chain 1, then optional 2-candle leg-out
        created = None
        d = _detect_at(o, h, l, c, i, 1)
        if d is not None:
            created = _create(zones, d, i, piv_h, piv_l)
        if created is None and not zone_on_prev and i >= 1:
            bull0, bull1 = c[i] > o[i], c[i - 1] > o[i - 1]
            bear0, bear1 = c[i] < o[i], c[i - 1] < o[i - 1]
            if ((bull0 and bull1) or (bear0 and bear1)) \
                    and _bp(o, h, l, c, i) > LEG_IN_BP and _bp(o, h, l, c, i - 1) > LEG_IN_BP:
                d = _detect_at(o, h, l, c, i, 2)
                if d is not None:
                    created = _create(zones, d, i, piv_h, piv_l)
        zone_on_prev = created is not None

        # 3. zone update: tests/fill -> mitigation -> arming
        for z in zones:
            if z.mitigated:
                continue
            idx_since = i - z.created_i
            countable = z.armed_prev
            touch = (l[i] <= z.prox_p) if z.is_demand else (h[i] >= z.prox_p)
            if countable:
                if touch and not z.in_zone:
                    z.tests += 1
                    if z.tests == 1:
                        fills.append({"i": i, "is_demand": z.is_demand,
                                      "fcode": z.fcode, "prox_p": z.prox_p,
                                      "distal": z.distal, "gap": z.gap})
                z.in_zone = touch
            if idx_since >= 1:
                if (c[i] < z.distal) if z.is_demand else (c[i] > z.distal):
                    z.mitigated = True
            z.armed_prev = idx_since >= SKIP_BARS
    return fills


def _val_blocked(fill: dict, score_v: np.ndarray | None, t1: float) -> bool:
    s_prev = score_v[fill["i"] - 1] if score_v is not None else np.nan
    if np.isnan(s_prev):
        return True
    return not (s_prev <= -t1) if fill["is_demand"] else not (s_prev >= t1)


def eval_strict(name: str, df: pd.DataFrame, fills: list[dict],
                score: pd.Series | None, t1: float, use_valuation: bool,
                target_r: float = 2.5, stop_pct: float = STOP_PCT,
                frictionless: bool = False) -> list[dict]:
    """Repo honest-fill convention (see module docstring)."""
    meta = {m["name"]: m for m in load_manifest()}[name]
    cost = cost_for(name, meta.get("jpy", False), meta["type"], meta["category"],
                    meta.get("tick"))
    friction = 0.0 if frictionless else (cost.spread_price + cost.slippage_price)
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    n = len(df)
    score_v = score.to_numpy() if score is not None else None
    trades: list[dict] = []
    in_pos_until = -1

    for f in fills:
        i = f["i"]
        if use_valuation and _val_blocked(f, score_v, t1):
            continue
        if i <= in_pos_until:
            continue
        dem = f["is_demand"]
        height = abs(f["prox_p"] - f["distal"])
        if height <= 0:
            continue
        sl = f["distal"] - stop_pct * height if dem else f["distal"] + stop_pct * height
        entry = f["prox_p"] + (friction if dem else -friction)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        tp = entry + (target_r * risk if dem else -target_r * risk)
        comm_r = 0.0 if frictionless else (2.0 * cost.commission_pct * entry / risk)

        if (l[i] <= sl) if dem else (h[i] >= sl):        # same-bar stopout
            trades.append({"instrument": name, "ts": idx[i], "side": "long" if dem else "short",
                           "fcode": f["fcode"], "r": -1.0 - comm_r, "bars": 0,
                           "reason": "SAME_BAR_SL", "entry": float(entry),
                           "sl": float(sl), "tp": float(tp), "entry_i": int(i)})
            in_pos_until = i
            continue

        r_out, bars_held, reason = None, 0, "EOS"
        for j in range(i + 1, min(n, i + 400)):
            bars_held = j - i
            if (l[j] <= sl) if dem else (h[j] >= sl):
                r_out, reason = -1.0, "SL"
                break
            if (h[j] >= tp) if dem else (l[j] <= tp):
                r_out, reason = target_r, "TP"
                break
        if r_out is None:
            last = min(n - 1, i + 399)
            r_out = ((c[last] - entry) / risk) if dem else ((entry - c[last]) / risk)
            bars_held = last - i
        trades.append({"instrument": name, "ts": idx[i], "side": "long" if dem else "short",
                       "fcode": f["fcode"], "r": float(r_out) - comm_r, "bars": bars_held,
                       "reason": reason, "entry": float(entry),
                       "sl": float(sl), "tp": float(tp), "entry_i": int(i)})
        in_pos_until = i + max(bars_held, 1)
    return trades


def eval_ledger(df: pd.DataFrame, fills: list[dict],
                score: pd.Series | None, t1: float, use_valuation: bool,
                tr1: float = 1.0, tr2: float = 2.0,
                stop_pct: float = STOP_PCT) -> list[dict]:
    """Replication of the indicator's on-chart virtual ledger: fill at the
    raw proximal, resolution starts ON the fill bar (same-bar TP counts),
    'Loss first' when SL+TP hit in one bar, costR=0, no position limit.
    Unresolved-at-end targets stay open (excluded)."""
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    n = len(df)
    idx = df.index
    score_v = score.to_numpy() if score is not None else None
    out: list[dict] = []
    for f in fills:
        if use_valuation and _val_blocked(f, score_v, t1):
            continue
        i = f["i"]
        dem = f["is_demand"]
        height = abs(f["prox_p"] - f["distal"])
        if height <= 0:
            continue
        entry = f["prox_p"]
        sl = f["distal"] - stop_pct * height if dem else f["distal"] + stop_pct * height
        risk = abs(entry - sl)
        res = {"ts": idx[i], "fcode": f["fcode"], "side": "long" if dem else "short"}
        for tag, tr in (("r1", tr1), ("r2", tr2)):
            tp = entry + tr * risk if dem else entry - tr * risk
            r_val = None
            for j in range(i, n):
                sl_hit = (l[j] <= sl) if dem else (h[j] >= sl)
                tp_hit = (h[j] >= tp) if dem else (l[j] <= tp)
                if sl_hit:                       # Loss first covers the tie
                    r_val = -1.0
                    break
                if tp_hit:
                    r_val = tr
                    break
            res[tag] = r_val                     # None = still open at EOS
        out.append(res)
    return out
