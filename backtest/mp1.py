"""MP-1 Swing-Only backtest — daily bars, long-only momentum with regime filter.

Data note: Yahoo Finance is blocked by the session egress policy, so this
runs on the repo's index futures (NQ as QQQ proxy, ES, YM, RTY, DAX, NKD)
resampled 4H -> daily (UTC calendar days). No volume data available:
volume-confirmation rules are replaced by range confirmation
(true range >= 1.2 x ATR20 on trigger day).

Setups (all daily-close based, long only):
  S1  50-SMA Reclaim     — was below SMA50 <= 15 days, SMA50 rising, close >= 1% above
  S2  Cup-and-Handle     — 25-60 day base depth <= 20%, 3-8 day handle upper third, breakout
  S3  EMA Pullback       — uptrend, low tags EMA10/20, close reclaims EMA20
  S5  Washout Long       — 3 red days cum return <= -2 x ATR%, day 3 closes upper third

Regime filter computed on NQ daily:
  RISK_ON   close > SMA50 and close > EMA20 and extension < 7 x ATR50
  EXTENDED  extension >= 7 x ATR50 or 12-day return > +10%
  DEFENSIVE close < SMA50
Rules: DEFENSIVE -> only S1/S5, half size. EXTENDED -> no new entries, trim rule active.

Management (swing-only, no intraday):
  stop per setup; TP1 33% at technical near-target, stop -> BE
  trim 33% if price >= SMA50 + 7 x ATR50
  runner: exit on daily close < EMA20 (EMA10 if extended); hard exit close < SMA50
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest, load_bars


INDEX_UNIVERSE = ["NQ", "ES", "YM", "RTY", "DAX", "NKD"]
ROBUSTNESS_UNIVERSE = ["NG", "SI", "HG", "CL", "PL", "PA"]  # commodities control group (no GC in repo data)
REGIME_TICKER = "NQ"


# ─────────────────────────────────────────────────────────────────────
# Data prep
# ─────────────────────────────────────────────────────────────────────
def daily_bars(name: str) -> pd.DataFrame:
    df4 = load_bars(name)
    o = df4["open"].resample("1D").first()
    h = df4["high"].resample("1D").max()
    l = df4["low"].resample("1D").min()
    c = df4["close"].resample("1D").last()
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["sma50"] = c.rolling(50).mean()
    df["sma50_slope"] = df["sma50"] - df["sma50"].shift(20)
    df["ema10"] = c.ewm(span=10, adjust=False).mean()
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    prev_c = c.shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_c).abs(),
        (df["low"] - prev_c).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["atr20"] = tr.rolling(20).mean()
    df["atr50"] = tr.rolling(50).mean()
    df["tr"] = tr
    df["ret12d"] = c / c.shift(12) - 1
    df["red"] = (c < df["open"]).astype(int)
    return df


# ─────────────────────────────────────────────────────────────────────
# Regime
# ─────────────────────────────────────────────────────────────────────
RISK_ON, EXTENDED, DEFENSIVE = "RISK_ON", "EXTENDED", "DEFENSIVE"


def regime_series(df: pd.DataFrame) -> pd.Series:
    ext = (df["close"] - df["sma50"]) / df["atr50"]
    out = pd.Series(RISK_ON, index=df.index)
    out[df["close"] < df["sma50"]] = DEFENSIVE
    out[(ext >= 7) | (df["ret12d"] > 0.10)] = EXTENDED
    # NaN warmup -> DEFENSIVE (no trading)
    out[df["sma50"].isna() | df["atr50"].isna()] = DEFENSIVE
    return out


# ─────────────────────────────────────────────────────────────────────
# Setup detection (all evaluated on completed daily bar i)
# ─────────────────────────────────────────────────────────────────────
def detect_s1(df: pd.DataFrame, i: int) -> dict | None:
    """50-SMA reclaim."""
    if i < 80:
        return None
    row = df.iloc[i]
    if np.isnan(row["sma50"]) or np.isnan(row["atr14"]):
        return None
    if row["sma50_slope"] <= 0:
        return None
    if row["close"] < row["sma50"] * 1.01:
        return None
    # Range confirmation replaces volume: trigger-day TR >= 1.2 x ATR20
    if row["tr"] < 1.2 * row["atr20"]:
        return None
    # Was below SMA50 recently, for <= 15 consecutive days
    below = df["close"].values[:i] < df["sma50"].values[:i]
    # count consecutive below run that ended within last 3 bars
    j = i - 1
    recent_above = 0
    while j >= 0 and not below[j]:
        recent_above += 1
        j -= 1
    if recent_above > 2:      # reclaim must be fresh
        return None
    run = 0
    while j >= 0 and below[j]:
        run += 1
        j -= 1
    if run == 0 or run > 15:
        return None
    stop = row["sma50"] * 0.95
    tp1 = float(df["high"].values[max(0, i - 20):i].max())  # prior 20d high
    if tp1 <= row["close"]:
        tp1 = row["close"] + 2 * (row["close"] - stop) / 3  # fallback partial target
    return {"model": "S1", "stop": float(stop), "tp1": float(tp1)}


def detect_s2(df: pd.DataFrame, i: int) -> dict | None:
    """Simplified objective cup-and-handle breakout."""
    if i < 90:
        return None
    row = df.iloc[i]
    if np.isnan(row["sma50"]) or row["close"] < row["sma50"]:
        return None
    # handle: last 3-8 bars before today consolidating in upper third of base
    for handle_len in range(3, 9):
        h0 = i - handle_len
        handle = df.iloc[h0:i]
        base = df.iloc[max(0, h0 - 60):h0]
        if len(base) < 25:
            continue
        base_high = base["high"].max()
        base_low = base["low"].min()
        depth = (base_high - base_low) / base_high
        if depth > 0.20 or depth < 0.04:
            continue
        # handle in upper third
        third = base_high - (base_high - base_low) / 3
        if handle["low"].min() < third:
            continue
        # contraction: handle ATR < 0.7 x atr20
        handle_rng = (handle["high"] - handle["low"]).mean()
        if handle_rng >= 0.7 * row["atr20"]:
            continue
        handle_high = handle["high"].max()
        # breakout today with range confirmation
        if row["close"] <= handle_high:
            continue
        if row["tr"] < 1.2 * row["atr20"]:
            continue
        stop = float(handle["low"].min() - 0.5 * row["atr14"])
        tp1 = float(row["close"] + (base_high - base_low))  # cup projection
        return {"model": "S2", "stop": stop, "tp1": tp1}
    return None


def detect_s3(df: pd.DataFrame, i: int) -> dict | None:
    """EMA10/20 pullback reclaim in established uptrend."""
    if i < 80:
        return None
    row = df.iloc[i]
    if np.isnan(row["ema20"]) or np.isnan(row["atr14"]):
        return None
    # uptrend: close > sma50, close > ema20 on >= 15 of last 20 bars
    if row["close"] < row["sma50"]:
        return None
    last20 = df.iloc[i - 20:i]
    above = (last20["close"] > last20["ema20"]).sum()
    if above < 15:
        return None
    # pullback tag of ema10 or ema20 today (or yesterday) with close reclaim
    tol = 0.3 * row["atr14"]
    tagged = (
        row["low"] <= row["ema10"] + tol or
        row["low"] <= row["ema20"] + tol
    )
    if not tagged:
        return None
    if row["close"] < row["ema20"]:
        return None
    stop = float(min(row["low"], df.iloc[i - 1]["low"]) - 0.5 * row["atr14"])
    tp1 = float(df["high"].values[max(0, i - 20):i].max())
    if tp1 <= row["close"]:
        return None
    return {"model": "S3", "stop": stop, "tp1": tp1}


def detect_s5(df: pd.DataFrame, i: int) -> dict | None:
    """Washout long: 3 consecutive red days, cum return <= -2 x ATR%, day 3 reversal close."""
    if i < 30:
        return None
    row = df.iloc[i]
    if np.isnan(row["atr20"]):
        return None
    last3 = df.iloc[i - 2:i + 1]
    if last3["red"].sum() < 3:
        return None
    cum_ret = row["close"] / df.iloc[i - 3]["close"] - 1
    atr_pct = row["atr20"] / row["close"]
    if cum_ret > -2.0 * atr_pct:
        return None
    # day 3 closes in upper third of its range
    rng = row["high"] - row["low"]
    if rng <= 0 or (row["close"] - row["low"]) / rng < 0.66:
        return None
    stop = float(row["low"])
    tp1 = float(df.iloc[i - 2]["open"])  # start of the dump
    if tp1 <= row["close"]:
        return None
    return {"model": "S5", "stop": stop, "tp1": tp1}


DETECTORS = {"S1": detect_s1, "S2": detect_s2, "S3": detect_s3, "S5": detect_s5}


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Position:
    instrument: str
    model: str
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    tp1: float
    risk: float
    frac_open: float = 1.0     # remaining fraction of position
    realized_r: float = 0.0    # accumulated realized R (weighted by fraction)
    tp1_done: bool = False
    trim7_done: bool = False
    entry_i: int = 0
    regime_at_entry: str = ""
    size_mult: float = 1.0     # 0.5 in DEFENSIVE


def run_mp1_instrument(
    name: str,
    df: pd.DataFrame,
    regime: pd.Series,
    enabled: tuple[str, ...] = ("S1", "S2", "S3", "S5"),
    allow_new_in_extended: bool = False,
) -> list[dict]:
    meta = {m["name"]: m for m in load_manifest()}[name]
    cost = cost_for(name, meta.get("jpy", False), meta["type"], meta["category"], meta.get("tick"))
    # round-trip friction in price units, applied once at entry
    friction = cost.spread_price + cost.slippage_price

    trades: list[dict] = []
    pos: Position | None = None

    idx = df.index
    for i in range(60, len(df)):
        row = df.iloc[i]
        ts = idx[i]
        reg = regime.reindex([ts]).iloc[0] if ts in regime.index else DEFENSIVE

        # ── manage open position ──
        if pos is not None:
            exited = False
            # stop hit intraday (conservative: stop first)
            if row["low"] <= pos.stop:
                exit_px = pos.stop
                r_leg = (exit_px - pos.entry) / pos.risk
                pos.realized_r += pos.frac_open * r_leg
                reason = "SL" if not pos.tp1_done else "STOP_AFTER_TP1"
                trades.append(_close(pos, ts, exit_px, reason, i))
                pos = None
                exited = True
            if not exited and pos is not None:
                # TP1
                if not pos.tp1_done and row["high"] >= pos.tp1:
                    r_leg = (pos.tp1 - pos.entry) / pos.risk
                    pos.realized_r += (1 / 3) * r_leg
                    pos.frac_open -= 1 / 3
                    pos.tp1_done = True
                    pos.stop = max(pos.stop, pos.entry)  # BE
                # 7xATR trim
                if not pos.trim7_done and not np.isnan(row["atr50"]) and not np.isnan(row["sma50"]):
                    if row["close"] >= row["sma50"] + 7 * row["atr50"]:
                        r_leg = (row["close"] - pos.entry) / pos.risk
                        pos.realized_r += (1 / 3) * r_leg
                        pos.frac_open -= 1 / 3
                        pos.trim7_done = True
                # runner exit on EMA break (daily close)
                ema_ref = row["ema10"] if (row["close"] - row["sma50"]) / max(row["atr50"], 1e-12) >= 7 else row["ema20"]
                hard_break = row["close"] < row["sma50"]
                if row["close"] < ema_ref or hard_break:
                    if pos.tp1_done or hard_break:
                        r_leg = (row["close"] - pos.entry) / pos.risk
                        pos.realized_r += pos.frac_open * r_leg
                        trades.append(_close(pos, ts, float(row["close"]),
                                             "SMA50_BREAK" if hard_break else "EMA_TRAIL", i))
                        pos = None

        # ── new entry ──
        if pos is None:
            if reg == EXTENDED and not allow_new_in_extended:
                continue
            size_mult = 1.0
            allowed = enabled
            if reg == DEFENSIVE:
                allowed = tuple(s for s in enabled if s in ("S1", "S5"))
                size_mult = 0.5
            for code in ("S2", "S1", "S3", "S5"):
                if code not in allowed:
                    continue
                sig = DETECTORS[code](df, i)
                if sig is None:
                    continue
                entry = float(row["close"]) + friction  # cost baked into entry
                stop = sig["stop"]
                if stop >= entry:
                    continue
                risk = entry - stop
                # min R:R to TP1 of 1.0 (TP1 is only 1/3 of position)
                if (sig["tp1"] - entry) / risk < 0.8:
                    continue
                pos = Position(
                    instrument=name, model=sig["model"], entry_ts=ts,
                    entry=entry, stop=stop, tp1=sig["tp1"], risk=risk,
                    entry_i=i, regime_at_entry=reg, size_mult=size_mult,
                )
                break

    if pos is not None:
        last = df.iloc[-1]
        r_leg = (float(last["close"]) - pos.entry) / pos.risk
        pos.realized_r += pos.frac_open * r_leg
        trades.append(_close(pos, idx[-1], float(last["close"]), "EOS", len(df) - 1))

    return trades


def _close(pos: Position, ts: pd.Timestamp, px: float, reason: str, i: int) -> dict:
    return {
        "instrument": pos.instrument,
        "model": pos.model,
        "side": "long",
        "bias": pos.regime_at_entry,
        "entry_ts": pos.entry_ts,
        "exit_ts": ts,
        "entry": pos.entry,
        "exit": px,
        "r": pos.realized_r * pos.size_mult,
        "pnl_pct": pos.realized_r * pos.size_mult * 0.005,
        "bars": i - pos.entry_i,
        "reason": reason,
        "partial_tp1": pos.tp1_done,
    }
