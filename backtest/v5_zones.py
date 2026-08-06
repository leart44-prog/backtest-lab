"""SD Zones v5 "Synthesis" — new detector built from the evidence of both
prior indicator studies. Parameters DECLARED before any results were seen.

Rules:
  Leg-out (bar i): |body| >= 0.60 x range AND (range >= 1.2 x ATR[i-1] OR
    gap-inclusive move from close[i-1] to the leg-out extreme >= 1.5 x
    ATR[i-1]). Wilder ATR(14). Direction = close vs open.
  Base: 1..4 candles before the leg-out (daily evidence: short bases).
    A candle is base if body <= 0.5 x range OR body <= 0.5 x ATR[j-1]
    (union of the course and v4 definitions). Consecutive, break otherwise.
  Speed bump (course rule): 1-candle base that is itself a strong
    same-direction candle -> reject.
  Formation: prior move within 8 bars before the base (v4 f_prior logic):
    decisive candle direction first, net-move fallback -> DBR/RBR/RBD/DBD,
    else fcode 0.
  Bounds: Preferred proximal = base BODY extreme; Wider proximal = base WICK
    extreme; distal includes the leg-out extreme (course rule).
  LoL (level-on-level): at creation, the zone overlaps OR lies within
    0.5 x ATR of an existing ACTIVE same-direction zone (not yet mitigated
    at that time, judged causally by close-through-distal up to creation).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .course_sd import CZone
from .v4_zones import _wilder_atr


def scan_v5_zones(df: pd.DataFrame,
                  body_frac: float = 0.60,
                  range_atr: float = 1.2,
                  gap_atr: float = 1.5,
                  base_body_frac: float = 0.5,
                  base_body_atr: float = 0.5,
                  max_base: int = 4,
                  prior_lb: int = 8,
                  lol_atr: float = 0.5) -> list[CZone]:
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    atr = _wilder_atr(h, l, c)
    body = np.abs(c - o)
    rng = h - l

    zones: list[CZone] = []
    # for causal LoL/active checks we track (zone, mitigation bar)
    mit_bar: dict[int, int] = {}

    def is_active(zi: int, at_bar: int) -> bool:
        z = zones[zi]
        mb = mit_bar.get(zi)
        return (mb is None or mb >= at_bar) and z.created_i < at_bar

    for i in range(30, n):
        a = atr[i - 1]
        if not np.isfinite(a) or a <= 0:
            continue
        bp = body[i] / rng[i] if rng[i] > 0 else 0.0
        big_range = rng[i] >= range_atr * a
        up_gap = (h[i] - c[i - 1]) >= gap_atr * a
        dn_gap = (c[i - 1] - l[i]) >= gap_atr * a
        leg_out_bull = c[i] > o[i] and bp >= body_frac and (big_range or up_gap)
        leg_out_bear = c[i] < o[i] and bp >= body_frac and (big_range or dn_gap)
        if not (leg_out_bull or leg_out_bear):
            continue
        is_dem = leg_out_bull

        # base scan
        b_cnt = 0
        b_hb = b_lb = b_hw = b_lw = None
        for k in range(1, max_base + 1):
            j = i - k
            if j < 1:
                break
            aj = atr[j - 1]
            base_by_range = rng[j] > 0 and body[j] <= base_body_frac * rng[j]
            base_by_atr = np.isfinite(aj) and aj > 0 and body[j] <= base_body_atr * aj
            if base_by_range or base_by_atr:
                b_hb = max(o[j], c[j]) if b_hb is None else max(b_hb, max(o[j], c[j]))
                b_lb = min(o[j], c[j]) if b_lb is None else min(b_lb, min(o[j], c[j]))
                b_hw = h[j] if b_hw is None else max(b_hw, h[j])
                b_lw = l[j] if b_lw is None else min(b_lw, l[j])
                b_cnt += 1
            else:
                break
        if b_cnt < 1:
            continue

        # speed bump: single base candle that is itself strong & same direction
        if b_cnt == 1:
            j = i - 1
            aj = atr[j - 1]
            strong = (np.isfinite(aj) and aj > 0 and body[j] >= range_atr * aj
                      and (body[j] / rng[j] if rng[j] > 0 else 0) >= body_frac)
            same_dir = (c[j] > o[j]) == is_dem
            if strong and same_dir:
                continue

        # prior-move formation (v4 logic)
        si = 1 + b_cnt
        prior_bull = prior_bear = False
        for k in range(si, min(si + prior_lb, i) + 1):
            j = i - k
            if j < 0:
                break
            aj = atr[j - 1] if j >= 1 else np.nan
            if (np.isfinite(aj) and aj > 0 and body[j] > aj * 0.5
                    and rng[j] > 0 and body[j] / rng[j] >= 0.4):
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
                if nm > a * 0.7:
                    prior_bull = True
                elif nm < -a * 0.7:
                    prior_bear = True

        if is_dem:
            fcode = 2 if prior_bear else (1 if prior_bull else 0)
            prox_p, prox_w = b_hb, b_hw
            distal = min(b_lw, l[i])
            if distal >= prox_p:
                continue
        else:
            fcode = 3 if prior_bull else (4 if prior_bear else 0)
            prox_p, prox_w = b_lb, b_lw
            distal = max(b_hw, h[i])
            if distal <= prox_p:
                continue

        # causal mitigation tracking for LoL activity checks
        # (fill mit_bar lazily for zones not yet resolved)
        lo1 = min(prox_p, distal)
        hi1 = max(prox_p, distal)
        lol = False
        for zi, z in enumerate(zones):
            if z.is_demand != is_dem:
                continue
            if zi not in mit_bar:
                mb = None
                for j2 in range(z.created_i + 1, n):
                    if (z.is_demand and c[j2] < z.distal) or ((not z.is_demand) and c[j2] > z.distal):
                        mb = j2
                        break
                mit_bar[zi] = mb if mb is not None else 10**9
            if not is_active(zi, i):
                continue
            lo2 = min(z.prox_p, z.distal)
            hi2 = max(z.prox_p, z.distal)
            overlap = hi1 >= lo2 and hi2 >= lo1
            gap = max(lo1 - hi2, lo2 - hi1)
            if overlap or (0 <= gap <= lol_atr * a):
                lol = True
                break

        zones.append(CZone(is_dem, fcode, float(prox_w), float(prox_p),
                           float(distal), i, 1, 1, lol=lol))
    return zones


def scan_v5_lol_only(df: pd.DataFrame) -> list[CZone]:
    return [z for z in scan_v5_zones(df) if z.lol]
