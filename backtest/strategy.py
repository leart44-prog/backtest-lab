"""Entry setups S-A / S-B / S-C / S-D.

All triggers adapted to 4H bars (finest available timeframe). References to
"1H-bars" in the spec map to 4H-bars here; counts scaled down by ~4x.

Each setup takes: current bar index i, bars-so-far slice (bars[:i+1]),
BiasState, and returns a Trade proposal (dict) or None.

A Trade proposal is a self-contained plan including entry, SL, TP1, TP2,
invalidation level, and metadata for the engine.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .bias import (
    BIAS_BULL_STRONG,
    BIAS_BEAR_STRONG,
    BIAS_NEUTRAL,
    BiasState,
)


@dataclass
class Trade:
    side: str           # "long" / "short"
    model: str          # "A" / "B" / "C" / "D"
    entry: float
    sl: float
    tp1: float
    tp2: float
    signal_ts: pd.Timestamp
    signal_bar_idx: int
    bias: str           # bias at signal


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _atr_4h(bars: pd.DataFrame, n: int = 14) -> float:
    if len(bars) < n + 1:
        return float(np.nan)
    h = bars["high"].values[-n - 1:]
    l = bars["low"].values[-n - 1:]
    c = bars["close"].values[-n - 1:]
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    return float(np.mean(tr[-n:]))


def _micro_swing_low(bars: pd.DataFrame, lookback: int = 6) -> float:
    """Lowest low of last `lookback` 4H bars BEFORE the current one."""
    if len(bars) < lookback + 1:
        return float(np.nan)
    return float(bars["low"].values[-lookback - 1:-1].min())


def _micro_swing_high(bars: pd.DataFrame, lookback: int = 6) -> float:
    if len(bars) < lookback + 1:
        return float(np.nan)
    return float(bars["high"].values[-lookback - 1:-1].max())


def _r_check(side: str, entry: float, sl: float, tp1: float, tp2: float,
             min_r_tp1: float = 1.3, min_r_tp2: float = 2.0) -> bool:
    risk = abs(entry - sl)
    if risk <= 0:
        return False
    if side == "long":
        r1 = (tp1 - entry) / risk
        r2 = (tp2 - entry) / risk
    else:
        r1 = (entry - tp1) / risk
        r2 = (entry - tp2) / risk
    return r1 >= min_r_tp1 and r2 >= min_r_tp2


def _find_next_hvn_above(price: float, hvns: list[tuple[float, float]]) -> float | None:
    above = sorted([h for h, _ in hvns if h > price])
    return above[0] if above else None


def _find_next_hvn_below(price: float, hvns: list[tuple[float, float]]) -> float | None:
    below = sorted([h for h, _ in hvns if h < price], reverse=True)
    return below[0] if below else None


# ─────────────────────────────────────────────────────────────────────
# Setup A — HTF-Trend-Pullback zum wPOC
# ─────────────────────────────────────────────────────────────────────
def setup_A(bars: pd.DataFrame, bias: BiasState, atr4h: float) -> Trade | None:
    if bias.bias not in (BIAS_BULL_STRONG, BIAS_BEAR_STRONG):
        return None
    if bias.wp is None or bias.mp is None or np.isnan(atr4h):
        return None

    current = bars.iloc[-1]
    price = float(current["close"])
    ts = bars.index[-1]
    wp = bias.wp
    mp = bias.mp

    # Require minimum separation from wPOC so we don't enter on top of entry zone
    if bias.bias == BIAS_BULL_STRONG:
        # Need recent wPOC tag and reclaim
        # Check last 2 4H bars (~ "4 x 1H window" from spec, scaled)
        lookback = bars.iloc[-3:]
        if len(lookback) < 3:
            return None
        touched = lookback["low"].min() <= wp.poc
        reclaim_bar = lookback.iloc[-1]
        reclaim = reclaim_bar["close"] > wp.poc
        # Non-doji
        rng = reclaim_bar["high"] - reclaim_bar["low"]
        if rng <= 0:
            return None
        body = abs(reclaim_bar["close"] - reclaim_bar["open"])
        non_doji = body > 0.25 * rng
        if not (touched and reclaim and non_doji):
            return None
        # Also require price to be sufficiently above wPOC on the bias side
        if price - wp.poc < 0.25 * atr4h:
            return None

        entry = price
        sl = min(wp.val, wp.poc - 1.0 * atr4h)
        tp1 = wp.vah
        tp2 = _find_next_hvn_above(entry, mp.hvns) or (mp.vah + 0.5 * (mp.vah - mp.poc))
        if tp2 <= tp1:
            tp2 = tp1 + max(atr4h, (tp1 - entry))
        if sl >= entry:
            return None
        if not _r_check("long", entry, sl, tp1, tp2):
            return None
        return Trade("long", "A", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)

    else:  # BEAR_STRONG
        lookback = bars.iloc[-3:]
        if len(lookback) < 3:
            return None
        touched = lookback["high"].max() >= wp.poc
        reclaim_bar = lookback.iloc[-1]
        reclaim = reclaim_bar["close"] < wp.poc
        rng = reclaim_bar["high"] - reclaim_bar["low"]
        if rng <= 0:
            return None
        body = abs(reclaim_bar["close"] - reclaim_bar["open"])
        non_doji = body > 0.25 * rng
        if not (touched and reclaim and non_doji):
            return None
        if wp.poc - price < 0.25 * atr4h:
            return None

        entry = price
        sl = max(wp.vah, wp.poc + 1.0 * atr4h)
        tp1 = wp.val
        tp2 = _find_next_hvn_below(entry, mp.hvns) or (mp.val - 0.5 * (mp.poc - mp.val))
        if tp2 >= tp1:
            tp2 = tp1 - max(atr4h, (entry - tp1))
        if sl <= entry:
            return None
        if not _r_check("short", entry, sl, tp1, tp2):
            return None
        return Trade("short", "A", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)


# ─────────────────────────────────────────────────────────────────────
# Setup B — Monthly-VA-Rejection (Range Fade)
# ─────────────────────────────────────────────────────────────────────
def setup_B(bars: pd.DataFrame, bias: BiasState, atr4h: float) -> Trade | None:
    if bias.bias != BIAS_NEUTRAL:
        return None
    if bias.mp is None or np.isnan(atr4h):
        return None

    mp = bias.mp
    # Width filter
    if mp.vah - mp.val < 1.5 * _atr_12h_proxy(atr4h):
        # 12H ATR ~ 1.5x 4H ATR as rough proxy; scale accordingly
        pass  # keep lenient

    current = bars.iloc[-1]
    price = float(current["close"])
    ts = bars.index[-1]

    # Check VAH rejection for short
    if len(bars) >= 3:
        tol = 0.25 * atr4h
        # Look at last 3 bars for touch
        last3 = bars.iloc[-3:]
        touched_vah = last3["high"].max() >= mp.vah - tol
        # Current bar closes back below VAH
        back_below = current["close"] < mp.vah
        if touched_vah and back_below:
            # Micro structure break: current low below swing low of prior 3 bars
            prior_swing_low = bars.iloc[-4:-1]["low"].min() if len(bars) >= 4 else bars.iloc[:-1]["low"].min()
            if current["low"] < prior_swing_low:
                rejection_high = last3["high"].max()
                entry = price
                sl = rejection_high + 0.5 * atr4h
                tp1 = mp.poc
                tp2 = mp.val
                if sl > entry and _r_check("short", entry, sl, tp1, tp2):
                    return Trade("short", "B", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)

        touched_val = last3["low"].min() <= mp.val + tol
        back_above = current["close"] > mp.val
        if touched_val and back_above:
            prior_swing_high = bars.iloc[-4:-1]["high"].max() if len(bars) >= 4 else bars.iloc[:-1]["high"].max()
            if current["high"] > prior_swing_high:
                rejection_low = last3["low"].min()
                entry = price
                sl = rejection_low - 0.5 * atr4h
                tp1 = mp.poc
                tp2 = mp.vah
                if sl < entry and _r_check("long", entry, sl, tp1, tp2):
                    return Trade("long", "B", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)

    return None


def _atr_12h_proxy(atr4h: float) -> float:
    return atr4h * 1.6


# ─────────────────────────────────────────────────────────────────────
# Setup C — LVN-Breakout-Retest
# ─────────────────────────────────────────────────────────────────────
def setup_C(bars: pd.DataFrame, bias: BiasState, atr4h: float) -> Trade | None:
    if bias.bias not in (BIAS_BULL_STRONG, BIAS_BEAR_STRONG):
        return None
    if bias.mp is None or np.isnan(atr4h):
        return None
    mp = bias.mp
    if not mp.lvns:
        return None

    current = bars.iloc[-1]
    price = float(current["close"])
    ts = bars.index[-1]

    if bias.bias == BIAS_BULL_STRONG:
        # LVNs below price
        candidates = sorted([lv for lv, _ in mp.lvns if lv < price], reverse=True)
        if not candidates:
            return None
        # Require LVN within reasonable retest distance (1..3 ATR below)
        lvn = None
        for lv in candidates:
            if 0.5 * atr4h <= (price - lv) <= 3.0 * atr4h:
                lvn = lv
                break
        if lvn is None:
            return None
        # Recent retest: low of last 5 bars <= lvn + 0.5*ATR
        lookback = bars.iloc[-5:]
        if lookback["low"].min() > lvn + 0.5 * atr4h:
            return None
        # Reclaim: current close > lvn + 0.25*ATR
        if current["close"] <= lvn + 0.25 * atr4h:
            return None

        entry = price
        sl = lvn - 0.5 * atr4h
        tp1 = _find_next_hvn_above(entry, mp.hvns) or mp.vah
        tp2 = mp.vah + 0.5 * (mp.vah - mp.poc)
        if tp2 <= tp1:
            tp2 = tp1 + atr4h
        if sl >= entry:
            return None
        if not _r_check("long", entry, sl, tp1, tp2):
            return None
        return Trade("long", "C", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)

    else:  # BEAR_STRONG
        candidates = sorted([lv for lv, _ in mp.lvns if lv > price])
        if not candidates:
            return None
        lvn = None
        for lv in candidates:
            if 0.5 * atr4h <= (lv - price) <= 3.0 * atr4h:
                lvn = lv
                break
        if lvn is None:
            return None
        lookback = bars.iloc[-5:]
        if lookback["high"].max() < lvn - 0.5 * atr4h:
            return None
        if current["close"] >= lvn - 0.25 * atr4h:
            return None

        entry = price
        sl = lvn + 0.5 * atr4h
        tp1 = _find_next_hvn_below(entry, mp.hvns) or mp.val
        tp2 = mp.val - 0.5 * (mp.poc - mp.val)
        if tp2 >= tp1:
            tp2 = tp1 - atr4h
        if sl <= entry:
            return None
        if not _r_check("short", entry, sl, tp1, tp2):
            return None
        return Trade("short", "C", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)


# ─────────────────────────────────────────────────────────────────────
# Setup D — Weekly-VA-Expansion
# ─────────────────────────────────────────────────────────────────────
def setup_D(bars: pd.DataFrame, bias: BiasState, atr4h: float) -> Trade | None:
    if bias.bias not in (BIAS_BULL_STRONG, BIAS_BEAR_STRONG):
        return None
    if bias.wp is None or bias.mp is None or np.isnan(atr4h):
        return None
    wp = bias.wp
    mp = bias.mp

    if len(bars) < 2:
        return None
    current = bars.iloc[-1]
    prev = bars.iloc[-2]
    price = float(current["close"])
    ts = bars.index[-1]

    if bias.bias == BIAS_BULL_STRONG:
        # Prev bar closed > wVAH; current bar makes higher high AND closes > wVAH
        if prev["close"] <= wp.vah:
            return None
        if current["high"] <= prev["high"]:
            return None
        if current["close"] <= wp.vah:
            return None
        entry = price
        sl = wp.poc - 0.25 * (wp.vah - wp.poc)
        if sl >= entry:
            sl = entry - 1.0 * atr4h
        risk = entry - sl
        tp1 = entry + 1.5 * risk
        tp2 = _find_next_hvn_above(entry, mp.hvns) or mp.vah
        if tp2 <= tp1:
            tp2 = tp1 + atr4h
        if not _r_check("long", entry, sl, tp1, tp2):
            return None
        return Trade("long", "D", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)

    else:  # BEAR_STRONG
        if prev["close"] >= wp.val:
            return None
        if current["low"] >= prev["low"]:
            return None
        if current["close"] >= wp.val:
            return None
        entry = price
        sl = wp.poc + 0.25 * (wp.poc - wp.val)
        if sl <= entry:
            sl = entry + 1.0 * atr4h
        risk = sl - entry
        tp1 = entry - 1.5 * risk
        tp2 = _find_next_hvn_below(entry, mp.hvns) or mp.val
        if tp2 >= tp1:
            tp2 = tp1 - atr4h
        if not _r_check("short", entry, sl, tp1, tp2):
            return None
        return Trade("short", "D", entry, sl, tp1, tp2, ts, len(bars) - 1, bias.bias)


SETUP_FUNCS = {
    "A": setup_A,
    "B": setup_B,
    "C": setup_C,
    "D": setup_D,
}
