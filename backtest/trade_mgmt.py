"""Generic trade-management replay engine.

Takes a fixed list of entry events and replays each one under several
management variants on the same bar data. Because entries are identical
across variants, differences in outcome are attributable to management
alone (paired comparison).

Entry event: dict(ts, side, entry, stop, atr, meta...)
Bars: DataFrame with open/high/low/close (+ ema10/ema20/sma50/atr14 columns).

Variants:
  M1_fix2R        set-and-forget, TP at 2R
  M2_fix3R        set-and-forget, TP at 3R
  M3_partial      50% off at 1R, stop->BE, rest to 3R
  M4_chandelier   BE at 1R, then chandelier trail 3xATR14 (no fixed TP)
  M5_mp1          1/3 off at 1.5R, stop->BE, rest EMA20-trail (close-based)
  M6_time10       TP 2R, hard exit after 10 trading bars (daily) / 60 bars (4H)

Conservative intrabar rule: if stop and target both touch in one bar, stop
fills first. Costs are baked into the entry price by the caller.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VARIANTS = ("M1_fix2R", "M2_fix3R", "M3_partial", "M4_chandelier", "M5_mp1", "M6_time10")


def replay(
    bars: pd.DataFrame,
    entry_i: int,
    side: str,
    entry: float,
    stop0: float,
    variant: str,
    time_stop_bars: int = 10,
    max_bars: int = 400,
) -> dict:
    """Replay one trade under one variant. Returns dict(r, bars_held, reason)."""
    sgn = 1.0 if side == "long" else -1.0
    risk = abs(entry - stop0)
    if risk <= 0:
        return {"r": 0.0, "bars_held": 0, "reason": "BAD"}

    stop = stop0
    frac = 1.0
    realized = 0.0
    partial_done = False
    hh = entry  # highest favorable extreme since entry (for chandelier)
    ll = entry

    tp = None
    if variant == "M1_fix2R":
        tp = entry + sgn * 2 * risk
    elif variant == "M2_fix3R":
        tp = entry + sgn * 3 * risk
    elif variant == "M3_partial":
        tp = entry + sgn * 3 * risk       # final target for the runner half
    elif variant == "M6_time10":
        tp = entry + sgn * 2 * risk

    partial_lvl = entry + sgn * 1.0 * risk      # M3/M4 breakeven trigger
    mp1_tp1 = entry + sgn * 1.5 * risk          # M5

    n = len(bars)
    end_i = min(n - 1, entry_i + max_bars)
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()
    atr14 = bars["atr14"].to_numpy() if "atr14" in bars else np.full(n, np.nan)
    ema20 = bars["ema20"].to_numpy() if "ema20" in bars else np.full(n, np.nan)

    for i in range(entry_i + 1, end_i + 1):
        hi, lo, cl = highs[i], lows[i], closes[i]
        hh = max(hh, hi)
        ll = min(ll, lo)
        held = i - entry_i

        adverse = lo if side == "long" else hi
        favorable = hi if side == "long" else lo

        # 1. stop first (conservative)
        stopped = (adverse <= stop) if side == "long" else (adverse >= stop)
        if stopped:
            r_leg = sgn * (stop - entry) / risk
            realized += frac * r_leg
            return {"r": realized, "bars_held": held,
                    "reason": "SL" if not partial_done and stop == stop0 else "STOP_MOVED"}

        # 2. partial triggers
        moved_this_bar = False
        if variant == "M3_partial" and not partial_done:
            hit = (favorable >= partial_lvl) if side == "long" else (favorable <= partial_lvl)
            if hit:
                realized += 0.5 * 1.0     # 50% at +1R
                frac = 0.5
                stop = entry              # BE
                partial_done = True
                moved_this_bar = True
        elif variant == "M4_chandelier" and not partial_done:
            hit = (favorable >= partial_lvl) if side == "long" else (favorable <= partial_lvl)
            if hit:
                stop = entry
                partial_done = True
                moved_this_bar = True
        elif variant == "M5_mp1" and not partial_done:
            hit = (favorable >= mp1_tp1) if side == "long" else (favorable <= mp1_tp1)
            if hit:
                realized += (1 / 3) * 1.5
                frac = 2 / 3
                stop = entry
                partial_done = True
                moved_this_bar = True

        # 2b. conservative same-bar check of the freshly moved stop: intrabar
        # ordering is unknowable, so assume the adverse extreme came AFTER the
        # favorable trigger — if it reaches the new stop, exit there.
        if moved_this_bar:
            hit_new = (adverse <= stop) if side == "long" else (adverse >= stop)
            if hit_new:
                r_leg = sgn * (stop - entry) / risk
                realized += frac * r_leg
                return {"r": realized, "bars_held": held, "reason": "BE_SAME_BAR"}

        # 3. fixed target
        if tp is not None:
            hit = (favorable >= tp) if side == "long" else (favorable <= tp)
            if hit:
                r_leg = sgn * (tp - entry) / risk
                realized += frac * r_leg
                return {"r": realized, "bars_held": held, "reason": "TP"}

        # 4. trails (close-based, applied after bar completes)
        if variant == "M4_chandelier" and partial_done and not np.isnan(atr14[i]):
            if side == "long":
                stop = max(stop, hh - 3.0 * atr14[i])
            else:
                stop = min(stop, ll + 3.0 * atr14[i])
        elif variant == "M5_mp1" and partial_done and not np.isnan(ema20[i]):
            crossed = (cl < ema20[i]) if side == "long" else (cl > ema20[i])
            if crossed:
                r_leg = sgn * (cl - entry) / risk
                realized += frac * r_leg
                return {"r": realized, "bars_held": held, "reason": "EMA_TRAIL"}

        # 5. time stop
        if variant == "M6_time10" and held >= time_stop_bars:
            r_leg = sgn * (cl - entry) / risk
            realized += frac * r_leg
            return {"r": realized, "bars_held": held, "reason": "TIME"}

    # end of data / max bars
    cl = closes[end_i]
    r_leg = sgn * (cl - entry) / risk
    realized += frac * r_leg
    return {"r": realized, "bars_held": end_i - entry_i, "reason": "EOS"}


def replay_all(bars: pd.DataFrame, entries: list[dict],
               time_stop_bars: int = 10) -> pd.DataFrame:
    """Replay every entry under every variant. Returns long-format DataFrame."""
    rows = []
    for e in entries:
        for v in VARIANTS:
            res = replay(bars, e["entry_i"], e["side"], e["entry"], e["stop"],
                         v, time_stop_bars=time_stop_bars)
            rows.append({
                "instrument": e["instrument"],
                "variant": v,
                "side": e["side"],
                "entry_ts": e["ts"],
                "r": res["r"],
                "bars_held": res["bars_held"],
                "reason": res["reason"],
                **{k: e[k] for k in e.get("extra_keys", [])},
            })
    return pd.DataFrame(rows)
