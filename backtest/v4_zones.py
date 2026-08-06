"""Python port of the user's Pine v5 "S&D Zones [v4]" detector.

Faithful mapping (defaults as in the script):
  - ATR(14) = Wilder RMA of true range (Pine ta.atr semantics!).
  - Impulse (leg-out, bar 0): bullish body > 1.0 x ATR with lower wick
    < 0.75 x body — or 2-candle variant: two consecutive bulls with summed
    bodies > 1.4 x ATR (then the base starts at offset 2). Bearish mirrored.
  - Base: consecutive candles BEFORE the impulse with small body
    (< 0.5 x ATR of that bar) OR indecisive (body/range < 0.5); max 6 on 4H
    (effMax rule), break on first non-base candle. bCnt >= 1 required.
  - Zone bounds (Preferred mode): demand top = base BODY high, demand bottom
    = absolute lowest low of impulse + base ("allLow", leg-out wick included);
    supply mirrored (bottom = base body low, top = absolute highest high).
  - Pattern via prior move (lookback 8 before the base): first decisive
    candle's direction, else net-move fallback (0.7 x ATR threshold):
    DBR/RBR for demand, RBD/DBD for supply; may be empty -> fcode 0.
  - Zone stays after a touch (greyed); deleted on close through the distal.
    (v4's extra rule — wick 25% BEYOND the distal deletes the zone — is
    approximated by the trade SL sitting exactly there; for untraded zones
    the engine keeps them slightly longer than v4 would. Documented deviation.)

Zones are emitted as CZone objects so the audited course_sd engine (fills,
gates, valuation, management) is reused unchanged — the only difference
between this study and the course-method study is the detector.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .course_sd import CZone


def _wilder_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr = np.full(len(tr), np.nan)
    if len(tr) < n + 1:
        return atr
    atr[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


def scan_v4_zones(df: pd.DataFrame,
                  imp_sens: float = 1.0,
                  base_max_body: float = 0.5,
                  max_wick_rat: float = 0.75,
                  max_base: int = 6,
                  prior_lb: int = 8,
                  include_cont: bool = True) -> list[CZone]:
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    atr = _wilder_atr(h, l, c)
    body = np.abs(c - o)
    up_wick = h - np.maximum(c, o)
    lo_wick = np.minimum(c, o) - l
    is_bull = c > o
    is_bear = c < o

    zones: list[CZone] = []
    for i in range(30, n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        bull1 = is_bull[i] and body[i] > a * imp_sens and lo_wick[i] < body[i] * max_wick_rat
        bear1 = is_bear[i] and body[i] > a * imp_sens and up_wick[i] < body[i] * max_wick_rat
        bull2 = is_bull[i] and is_bull[i - 1] and (body[i] + body[i - 1]) > a * imp_sens * 1.4
        bear2 = is_bear[i] and is_bear[i - 1] and (body[i] + body[i - 1]) > a * imp_sens * 1.4
        bull_imp = bull1 or bull2
        bear_imp = bear1 or bear2
        if not (bull_imp or bear_imp):
            continue

        base_start = 1
        if bull2 and not bull1:
            base_start = 2
        if bear2 and not bear1:
            base_start = 2

        # base scan (consecutive small-body or indecisive candles)
        b_cnt = 0
        b_hb = b_lb = b_hw = b_lw = None
        for k in range(base_start, min(base_start + max_base, i)):
            j = i - k
            c_atr = atr[j]
            small_body = np.isfinite(c_atr) and c_atr > 0 and body[j] < c_atr * base_max_body
            rng_j = h[j] - l[j]
            indecisive = rng_j > 0 and (body[j] / rng_j) < 0.5
            if small_body or indecisive:
                body_hi = max(o[j], c[j])
                body_lo = min(o[j], c[j])
                b_hb = body_hi if b_hb is None else max(b_hb, body_hi)
                b_lb = body_lo if b_lb is None else min(b_lb, body_lo)
                b_hw = h[j] if b_hw is None else max(b_hw, h[j])
                b_lw = l[j] if b_lw is None else min(b_lw, l[j])
                b_cnt += 1
            else:
                break
        if b_cnt < 1:
            continue

        # absolute extremes across impulse + base ("allLow"/"allHigh")
        span_lo = min(l[i - (base_start + b_cnt - 1):i + 1])
        span_hi = max(h[i - (base_start + b_cnt - 1):i + 1])

        # prior-move pattern
        si = base_start + b_cnt
        prior_bull = prior_bear = False
        for k in range(si, min(si + prior_lb, i) + 1):
            j = i - k
            if j < 0:
                break
            c_atr = atr[j]
            rng_j = h[j] - l[j]
            if (np.isfinite(c_atr) and c_atr > 0 and body[j] > c_atr * imp_sens * 0.5
                    and rng_j > 0 and body[j] / rng_j >= 0.4):
                if c[j] > o[j]:
                    prior_bull = True
                else:
                    prior_bear = True
                break
        if not prior_bull and not prior_bear:
            j_far = i - min(si + prior_lb, i)
            j_near = i - si
            if j_far >= 0 and j_near >= 0:
                nm = c[j_near] - c[j_far]
                mm = a * imp_sens * 0.7
                if nm > mm:
                    prior_bull = True
                elif nm < -mm:
                    prior_bear = True

        if bull_imp:
            fcode = 2 if prior_bear else (1 if prior_bull else 0)
            if not include_cont and fcode == 1:
                continue
            prox_p = b_hb            # Preferred: base body high
            prox_w = b_hw
            distal = span_lo
            if prox_p is None or distal >= prox_p:
                continue
            zones.append(CZone(True, fcode, float(prox_w), float(prox_p),
                               float(distal), i, 1, 1))
        if bear_imp:
            fcode = 3 if prior_bull else (4 if prior_bear else 0)
            if not include_cont and fcode == 4:
                continue
            prox_p = b_lb            # Preferred: base body low
            prox_w = b_lw
            distal = span_hi
            if prox_p is None or distal <= prox_p:
                continue
            zones.append(CZone(False, fcode, float(prox_w), float(prox_p),
                               float(distal), i, 1, 1))
    return zones
