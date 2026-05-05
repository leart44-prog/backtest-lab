"""Bias classification from Monthly + Weekly profiles.

Objective thresholds from strategy §2. Uses PREVIOUS completed period profiles
only — no lookahead.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .profile import Profile, applicable_monthly, applicable_weekly

BIAS_BULL_STRONG = "BULL_STRONG"
BIAS_BULL_WEAK = "BULL_WEAK"
BIAS_NEUTRAL = "NEUTRAL"
BIAS_BEAR_WEAK = "BEAR_WEAK"
BIAS_BEAR_STRONG = "BEAR_STRONG"
BIAS_CONFLICT = "CONFLICT"
BIAS_NONE = "NONE"


@dataclass
class BiasState:
    bias: str
    mp: Profile | None
    wp: Profile | None
    price: float
    closes_above_vah: int   # consecutive recent 12H closes above mVAH
    closes_below_val: int


def classify_bias(
    ts: pd.Timestamp,
    price: float,
    monthly_profs: dict,
    weekly_profs: dict,
    recent_closes_12h: list[float],
) -> BiasState:
    """Compute bias at timestamp ts with current price.

    recent_closes_12h: last N 12H closes up to and including the prior closed bar.
    """
    mp = applicable_monthly(ts, monthly_profs)
    wp = applicable_weekly(ts, weekly_profs)

    if mp is None or wp is None:
        return BiasState(BIAS_NONE, mp, wp, price, 0, 0)

    # Count consecutive 12H closes above mVAH / below mVAL (ending at prior bar)
    closes_above = 0
    for c in reversed(recent_closes_12h):
        if c > mp.vah:
            closes_above += 1
        else:
            break
    closes_below = 0
    for c in reversed(recent_closes_12h):
        if c < mp.val:
            closes_below += 1
        else:
            break

    # Conflict check
    if price > mp.vah and wp.poc < mp.val:
        return BiasState(BIAS_CONFLICT, mp, wp, price, closes_above, closes_below)
    if price < mp.val and wp.poc > mp.vah:
        return BiasState(BIAS_CONFLICT, mp, wp, price, closes_above, closes_below)

    # Bullish Strong
    if price > mp.vah and closes_above >= 3 and wp.poc > mp.poc:
        return BiasState(BIAS_BULL_STRONG, mp, wp, price, closes_above, closes_below)

    # Bearish Strong
    if price < mp.val and closes_below >= 3 and wp.poc < mp.poc:
        return BiasState(BIAS_BEAR_STRONG, mp, wp, price, closes_above, closes_below)

    # Bullish Weak
    if mp.poc < price <= mp.vah and wp.poc > mp.poc:
        return BiasState(BIAS_BULL_WEAK, mp, wp, price, closes_above, closes_below)

    # Bearish Weak
    if mp.val <= price < mp.poc and wp.poc < mp.poc:
        return BiasState(BIAS_BEAR_WEAK, mp, wp, price, closes_above, closes_below)

    # Neutral
    inside_mva = mp.val <= price <= mp.vah
    poc_spread = abs(wp.poc - mp.poc)
    mva_width = mp.vah - mp.val
    if inside_mva and mva_width > 0 and poc_spread < 0.25 * mva_width:
        return BiasState(BIAS_NEUTRAL, mp, wp, price, closes_above, closes_below)

    # Fallback: weak alignment
    if price > mp.poc and wp.poc >= mp.poc:
        return BiasState(BIAS_BULL_WEAK, mp, wp, price, closes_above, closes_below)
    if price < mp.poc and wp.poc <= mp.poc:
        return BiasState(BIAS_BEAR_WEAK, mp, wp, price, closes_above, closes_below)

    return BiasState(BIAS_NEUTRAL, mp, wp, price, closes_above, closes_below)
