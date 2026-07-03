"""Objective supply & demand zone detection on 4H bars.

Zone definition (demand; supply mirrored):
  - Base: 1-3 consecutive bars each with range <= 0.8 x ATR14 ("pause").
  - Departure: the 2 bars after the base are bullish closes and their combined
    close-to-close move >= 1.5 x ATR14 (impulsive leave).
  - Zone = [base low, base high]. Created at the close of the departure's
    2nd bar (no lookahead: all bars completed).
  - Valid for the FIRST retest only, within 240 bars (~40 trading days).
  - Trend filter: longs only if close > daily-equivalent SMA (SMA of 4H close,
    300 bars ~ 50 days) and its slope up; shorts mirrored.

Entry model (limit at proximal edge):
  - Long: limit at zone high, stop below zone low - 0.25 x ATR14.
  - Entry counts as filled if a later bar trades through the proximal edge
    while the zone is still fresh. Fill price = proximal edge (+ costs).
  - Skip if the same bar that touches the zone also breaks its far edge
    (zone violated immediately -> no trade, conservative).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest, load_bars


def find_zone_touches(name: str, df: pd.DataFrame,
                      max_zone_age: int = 240) -> list[dict]:
    """Raw first-touch signals (order-type agnostic).

    A signal is emitted when a fresh zone's proximal edge is touched while the
    trend filter passes. What happens next (limit fill, stop trigger, close
    confirmation) is the entry model's business — see entry_models.py.
    Signal fields: touch_i, side, proximal, far, atr (at touch), sl_level.
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    atr = df["atr14"].to_numpy()
    sma = df["sma300"].to_numpy()
    slope = df["sma300_slope"].to_numpy()
    idx = df.index
    n = len(df)

    signals: list[dict] = []
    zones: list[dict] = []

    for i in range(320, n):
        if np.isnan(atr[i]) or np.isnan(sma[i]):
            continue
        # NB: SL level and buffer ATR use atr[i-1] — the last COMPLETED bar
        # before the touch. A resting limit fills mid-bar; the touch bar's own
        # ATR is not knowable at fill time (audit finding: pro-strategy leak).
        atr_known = atr[i - 1]
        if np.isnan(atr_known):
            continue
        still = []
        for z in zones:
            if i - z["created_i"] > max_zone_age:
                continue
            if z["side"] == "long":
                touched = l[i] <= z["proximal"]
                trend_ok = c[i - 1] > sma[i - 1] and slope[i - 1] > 0
                if touched:
                    sl_level = z["far"] - 0.25 * atr_known
                    if trend_ok and sl_level < z["proximal"]:
                        signals.append({
                            "instrument": name, "ts": idx[i], "touch_i": i,
                            "side": "long", "proximal": float(z["proximal"]),
                            "far": float(z["far"]), "atr": float(atr_known),
                            "sl_level": float(sl_level),
                        })
                    continue
            else:
                touched = h[i] >= z["proximal"]
                trend_ok = c[i - 1] < sma[i - 1] and slope[i - 1] < 0
                if touched:
                    sl_level = z["far"] + 0.25 * atr_known
                    if trend_ok and sl_level > z["proximal"]:
                        signals.append({
                            "instrument": name, "ts": idx[i], "touch_i": i,
                            "side": "short", "proximal": float(z["proximal"]),
                            "far": float(z["far"]), "atr": float(atr_known),
                            "sl_level": float(sl_level),
                        })
                    continue
            still.append(z)
        zones = still

        for base_len in (1, 2, 3):
            b0 = i - 1 - base_len
            if b0 < 1:
                continue
            base_h = h[b0:i - 1].max()
            base_l = l[b0:i - 1].min()
            base_ok = all((h[j] - l[j]) <= 0.8 * atr[j] for j in range(b0, i - 1)
                          if not np.isnan(atr[j]))
            if not base_ok:
                continue
            move = c[i] - c[b0 - 1]
            if c[i - 1] > o[i - 1] and c[i] > o[i] and move >= 1.5 * atr[i]:
                zones.append({"side": "long", "proximal": base_h, "far": base_l,
                              "created_i": i})
                break
            if c[i - 1] < o[i - 1] and c[i] < o[i] and -move >= 1.5 * atr[i]:
                zones.append({"side": "short", "proximal": base_l, "far": base_h,
                              "created_i": i})
                break

    return signals


def prep_4h(name: str) -> pd.DataFrame:
    df = load_bars(name).copy()
    c = df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev_c).abs(),
                    (df["low"] - prev_c).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["sma300"] = c.rolling(300).mean()          # ~50 daily bars
    df["sma300_slope"] = df["sma300"] - df["sma300"].shift(60)
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    return df


def find_sd_entries(name: str, df: pd.DataFrame,
                    max_zone_age: int = 240) -> list[dict]:
    """Detect S/D zones and their first-retest limit fills."""
    meta = {m["name"]: m for m in load_manifest()}[name]
    cost = cost_for(name, meta.get("jpy", False), meta["type"], meta["category"], meta.get("tick"))
    friction = cost.spread_price + cost.slippage_price

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    atr = df["atr14"].to_numpy()
    sma = df["sma300"].to_numpy()
    slope = df["sma300_slope"].to_numpy()
    idx = df.index
    n = len(df)

    entries: list[dict] = []
    zones: list[dict] = []   # active, waiting for first retest

    for i in range(320, n):
        if np.isnan(atr[i]) or np.isnan(sma[i]):
            continue

        # ── check active zones for retest fill on bar i ──
        still = []
        for z in zones:
            age = i - z["created_i"]
            if age > max_zone_age:
                continue
            if z["side"] == "long":
                touched = l[i] <= z["proximal"]
                violated = l[i] <= z["far"] - 0.25 * atr[i]
                # trend filter at fill time
                trend_ok = c[i - 1] > sma[i - 1] and slope[i - 1] > 0
                if touched:
                    if trend_ok:
                        entry_px = z["proximal"] + friction
                        stop = z["far"] - 0.25 * atr[i]
                        if stop < entry_px:
                            # A resting limit order fills on the touch. If the
                            # same bar also trades through the stop, that is a
                            # real -1R loss, not a skippable event.
                            entries.append({
                                "instrument": name, "ts": idx[i], "entry_i": i,
                                "side": "long", "entry": float(entry_px),
                                "stop": float(stop), "atr": float(atr[i]),
                                "violated": bool(violated),
                            })
                    continue    # zone consumed (touched), drop it either way
            else:
                touched = h[i] >= z["proximal"]
                violated = h[i] >= z["far"] + 0.25 * atr[i]
                trend_ok = c[i - 1] < sma[i - 1] and slope[i - 1] < 0
                if touched:
                    if trend_ok:
                        entry_px = z["proximal"] - friction
                        stop = z["far"] + 0.25 * atr[i]
                        if stop > entry_px:
                            entries.append({
                                "instrument": name, "ts": idx[i], "entry_i": i,
                                "side": "short", "entry": float(entry_px),
                                "stop": float(stop), "atr": float(atr[i]),
                                "violated": bool(violated),
                            })
                    continue
            still.append(z)
        zones = still

        # ── detect new zone completed at bar i (departure 2nd bar = i) ──
        # departure bars: i-1, i  (both must close directionally)
        for base_len in (1, 2, 3):
            b0 = i - 1 - base_len   # base start
            if b0 < 1:
                continue
            base_h = h[b0:i - 1].max()
            base_l = l[b0:i - 1].min()
            base_ok = all((h[j] - l[j]) <= 0.8 * atr[j] for j in range(b0, i - 1)
                          if not np.isnan(atr[j]))
            if not base_ok:
                continue
            move = c[i] - c[b0 - 1]
            # demand: two bullish closes, impulsive up-move
            if c[i - 1] > o[i - 1] and c[i] > o[i] and move >= 1.5 * atr[i]:
                zones.append({"side": "long", "proximal": base_h, "far": base_l,
                              "created_i": i})
                break
            # supply: two bearish closes, impulsive down-move
            if c[i - 1] < o[i - 1] and c[i] < o[i] and -move >= 1.5 * atr[i]:
                zones.append({"side": "short", "proximal": base_l, "far": base_h,
                              "created_i": i})
                break

    return entries
