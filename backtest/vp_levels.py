"""Volume-weighted weekly/monthly profiles from the Dukascopy 1H cache.

Same design as profile.py (calendar-anchored, lookahead-safe: a bar in
period P uses the PREVIOUS completed period's profile) but weighted with
Dukascopy tick volume: each 1H bar distributes its volume uniformly over
the price bins its [low, high] range spans (TPO fallback weight 1 when a
bar carries no volume). Bin size = 0.10 x period ATR, value area 70%.
"""
from __future__ import annotations

import glob
import lzma
import os
import struct
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class VPLevels:
    start: pd.Timestamp        # period start (profile built FROM this period)
    poc: float
    vah: float
    val: float
    va_h: float                # VAH - VAL
    p_min: float
    p_max: float


def load_dukas_1h(pair: str, cache: str | None = None) -> pd.DataFrame:
    """1H bars incl. tick volume from the monthly bi5 cache."""
    cache = cache or os.environ.get("DUKAS_CACHE", "")
    scale = 1e3 if "JPY" in pair else 1e5
    rows = []
    for path in sorted(glob.glob(os.path.join(cache, pair, "*.bi5"))):
        y, m = os.path.basename(path)[:-4].split("-")
        raw = lzma.decompress(open(path, "rb").read())
        base = pd.Timestamp(year=int(y), month=int(m) + 1, day=1, tz="UTC")
        for k in range(len(raw) // 24):
            t, o, c, l, h, v = struct.unpack(">5if", raw[k * 24:(k + 1) * 24])
            if v == 0 and h == l:
                continue
            rows.append((base + pd.Timedelta(seconds=t), o / scale, h / scale,
                         l / scale, c / scale, float(v)))
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol"])
    df = df.set_index("ts").sort_index()
    return df[df.index.dayofweek <= 4]


def _profile(period: pd.DataFrame, bin_frac_atr: float = 0.10,
             va_pct: float = 0.70) -> tuple[float, float, float, float, float] | None:
    if len(period) < 20:
        return None
    highs = period["high"].to_numpy()
    lows = period["low"].to_numpy()
    closes = period["close"].to_numpy()
    vols = period["vol"].to_numpy()
    prev_close = np.concatenate([[closes[0]], closes[:-1]])
    atr = float(np.mean(np.maximum.reduce([highs - lows, np.abs(highs - prev_close),
                                           np.abs(lows - prev_close)])))
    if not np.isfinite(atr) or atr <= 0:
        return None
    bin_size = bin_frac_atr * atr
    p_min, p_max = float(lows.min()), float(highs.max())
    if p_max <= p_min:
        return None
    n_bins = int(np.ceil((p_max - p_min) / bin_size)) + 1
    if n_bins < 3 or n_bins > 20000:
        return None
    counts = np.zeros(n_bins)
    for lo, hi, v in zip(lows, highs, vols):
        i0 = max(0, min(n_bins - 1, int((lo - p_min) / bin_size)))
        i1 = max(0, min(n_bins - 1, int((hi - p_min) / bin_size)))
        w = v if v > 0 else 1.0
        counts[i0:i1 + 1] += w / (i1 - i0 + 1)   # volume spread over spanned bins
    total = counts.sum()
    if total <= 0:
        return None
    poc_idx = int(np.argmax(counts))
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
    edges = p_min + bin_size * np.arange(n_bins + 1)
    poc = float(edges[poc_idx] + bin_size / 2.0)
    val = float(edges[lo_idx])
    vah = float(edges[hi_idx + 1])
    return poc, vah, val, p_min, p_max


def build_levels(h1: pd.DataFrame, freq: str) -> dict[pd.Timestamp, VPLevels]:
    """freq 'W' (ISO week, Mon 00:00 UTC) or 'M' (calendar month).
    Key = period start; only COMPLETED periods (data exists after end)."""
    out: dict[pd.Timestamp, VPLevels] = {}
    if h1.empty:
        return out
    naive = h1.index.tz_convert(None)
    periods = naive.to_period("W-SUN" if freq == "W" else "M").unique()
    last = h1.index[-1]
    for p in periods:
        start = pd.Timestamp(p.to_timestamp(how="start"), tz="UTC")
        end = pd.Timestamp((p + 1).to_timestamp(how="start"), tz="UTC")
        if end > last:
            continue
        res = _profile(h1[(h1.index >= start) & (h1.index < end)])
        if res is None:
            continue
        poc, vah, val, p_min, p_max = res
        out[start] = VPLevels(start, poc, vah, val, vah - val, p_min, p_max)
    return out


def applicable(ts: pd.Timestamp, levels: dict[pd.Timestamp, VPLevels],
               freq: str) -> VPLevels | None:
    """Previous COMPLETED period's levels for a bar at ts (causal)."""
    if freq == "W":
        cur = (ts - pd.Timedelta(days=ts.weekday())).normalize()
        return levels.get(cur - pd.Timedelta(days=7))
    cur = pd.Timestamp(year=ts.year, month=ts.month, day=1, tz="UTC")
    prev_end = cur - pd.Timedelta(seconds=1)
    return levels.get(pd.Timestamp(year=prev_end.year, month=prev_end.month, day=1, tz="UTC"))
