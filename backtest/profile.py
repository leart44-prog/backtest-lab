"""TPO Volume Profile computation — calendar-anchored, lookahead-safe.

Design decisions:
- TPO approach: each bar contributes weight 1 to every price bin it touches
  (floor(low/bin) .. floor(high/bin)). This is the honest choice given we
  don't have tick volume.
- Calendar anchoring: monthly profiles anchored to calendar month boundaries,
  weekly profiles to ISO week (Mon 00:00 UTC).
- Lookahead safety: at any signal bar t, the applicable profile is the
  PREVIOUS fully-completed calendar period's profile. No partial-period
  profiles. This is conservative but matches what a live trader sees at
  period-boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Profile:
    start: pd.Timestamp
    end: pd.Timestamp
    poc: float
    vah: float
    val: float
    bin_size: float
    atr: float
    hvns: list[tuple[float, float]]   # (price, count) — top HVNs outside VA
    lvns: list[tuple[float, float]]   # (price, count) — top LVNs within range
    price_min: float
    price_max: float


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> float:
    if len(highs) < 2:
        return float(np.mean(highs - lows))
    prev_close = np.concatenate([[closes[0]], closes[:-1]])
    tr = np.maximum.reduce([
        highs - lows,
        np.abs(highs - prev_close),
        np.abs(lows - prev_close),
    ])
    return float(np.mean(tr))


def compute_profile(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    bin_frac_atr: float = 0.10,
    va_pct: float = 0.70,
) -> Profile | None:
    """Compute TPO profile for bars with timestamps in [start, end).

    Returns None if too few bars.
    """
    mask = (df.index >= start) & (df.index < end)
    period = df.loc[mask]
    if len(period) < 5:
        return None

    highs = period["high"].to_numpy()
    lows = period["low"].to_numpy()
    closes = period["close"].to_numpy()
    atr = _atr(highs, lows, closes)
    if not np.isfinite(atr) or atr <= 0:
        return None

    bin_size = bin_frac_atr * atr
    p_min = float(np.min(lows))
    p_max = float(np.max(highs))
    if p_max <= p_min:
        return None
    n_bins = int(np.ceil((p_max - p_min) / bin_size)) + 1
    if n_bins < 3:
        return None

    counts = np.zeros(n_bins, dtype=np.float64)
    bin_edges = p_min + bin_size * np.arange(n_bins + 1)

    # TPO vote: each bar votes 1 for each bin it spans.
    for lo, hi in zip(lows, highs):
        i0 = int((lo - p_min) / bin_size)
        i1 = int((hi - p_min) / bin_size)
        i0 = max(0, min(n_bins - 1, i0))
        i1 = max(0, min(n_bins - 1, i1))
        counts[i0:i1 + 1] += 1.0

    # POC
    poc_idx = int(np.argmax(counts))
    poc = bin_edges[poc_idx] + bin_size / 2.0

    # Value Area: expand around POC until 70% of total counts covered.
    total = counts.sum()
    if total <= 0:
        return None
    target = total * va_pct
    lo_idx, hi_idx = poc_idx, poc_idx
    included = counts[poc_idx]
    while included < target:
        left = counts[lo_idx - 1] if lo_idx > 0 else -1.0
        right = counts[hi_idx + 1] if hi_idx < n_bins - 1 else -1.0
        if left < 0 and right < 0:
            break
        if left >= right:
            lo_idx -= 1
            included += counts[lo_idx]
        else:
            hi_idx += 1
            included += counts[hi_idx]
    val = float(bin_edges[lo_idx])
    vah = float(bin_edges[hi_idx + 1])

    # HVN / LVN thresholds relative to POC count
    poc_vol = counts[poc_idx]
    hvns = []
    lvns = []
    for i in range(n_bins):
        mid = bin_edges[i] + bin_size / 2.0
        v = counts[i]
        if v >= 0.70 * poc_vol and (i < lo_idx or i > hi_idx):
            hvns.append((float(mid), float(v)))
        if 0 < v <= 0.30 * poc_vol:
            lvns.append((float(mid), float(v)))
    hvns.sort(key=lambda x: -x[1])
    hvns = hvns[:5]

    return Profile(
        start=start, end=end,
        poc=poc, vah=vah, val=val,
        bin_size=bin_size, atr=atr,
        hvns=hvns, lvns=lvns,
        price_min=p_min, price_max=p_max,
    )


def monthly_profiles(df_12h: pd.DataFrame) -> dict[pd.Timestamp, Profile]:
    """Build completed monthly profiles from 12H bars. Key = month-start UTC.

    Only COMPLETED months get a profile (current month excluded — no lookahead).
    """
    out: dict[pd.Timestamp, Profile] = {}
    if df_12h.empty:
        return out
    months = df_12h.index.tz_convert(None).to_period("M").unique()
    for pm in months:
        start = pd.Timestamp(pm.to_timestamp(how="start"), tz="UTC")
        end = pd.Timestamp((pm + 1).to_timestamp(how="start"), tz="UTC")
        # Only count as completed if we have data AFTER this month ends
        if end > df_12h.index[-1]:
            continue
        prof = compute_profile(df_12h, start, end, bin_frac_atr=0.10, va_pct=0.70)
        if prof is not None:
            out[start] = prof
    return out


def weekly_profiles(df_4h: pd.DataFrame) -> dict[pd.Timestamp, Profile]:
    """Build completed weekly profiles from 4H bars. Key = ISO week-start (Mon 00:00 UTC)."""
    out: dict[pd.Timestamp, Profile] = {}
    if df_4h.empty:
        return out
    # Anchor to Monday 00:00 UTC
    index = df_4h.index
    weeks = index.tz_convert(None).to_period("W-SUN").unique()
    for pw in weeks:
        start = pd.Timestamp(pw.to_timestamp(how="start"), tz="UTC")
        end = pd.Timestamp((pw + 1).to_timestamp(how="start"), tz="UTC")
        if end > df_4h.index[-1]:
            continue
        prof = compute_profile(df_4h, start, end, bin_frac_atr=0.10, va_pct=0.70)
        if prof is not None:
            out[start] = prof
    return out


# ─────────────────────────────────────────────────────────────────────
# Lookup helpers: given a bar timestamp, find the applicable prior profile
# ─────────────────────────────────────────────────────────────────────
def applicable_monthly(ts: pd.Timestamp, profiles: dict[pd.Timestamp, Profile]) -> Profile | None:
    """Return the previous completed month's profile for bar at ts."""
    # Current month starts at:
    current_month = pd.Timestamp(year=ts.year, month=ts.month, day=1, tz="UTC")
    # We want the previous month's profile: month start minus 1 day, floor to month start
    prev_end = current_month - pd.Timedelta(seconds=1)
    prev_start = pd.Timestamp(year=prev_end.year, month=prev_end.month, day=1, tz="UTC")
    return profiles.get(prev_start)


def applicable_weekly(ts: pd.Timestamp, profiles: dict[pd.Timestamp, Profile]) -> Profile | None:
    """Return the previous completed week's profile for bar at ts."""
    # ISO week start (Monday)
    weekday = ts.weekday()  # Mon=0
    current_week_start = (ts - pd.Timedelta(days=weekday)).normalize()
    prev_week_start = current_week_start - pd.Timedelta(days=7)
    return profiles.get(prev_week_start)
