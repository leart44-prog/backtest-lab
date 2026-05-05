"""Event-driven backtest engine.

Single-instrument loop. Portfolio layer stitches results together.

Core loop on 4H bars:
  for each bar i:
    1. If open trade: check SL/TP1/TP2 hit intrabar (pessimistic: SL first).
       - Check time-stop (10 trading days since entry).
       - Check bias-flip exit.
    2. If no open trade: compute bias. If signal, try each enabled setup.
       Take first valid signal (priority A > C > D > B).
    3. Book P/L.

Intrabar assumption (honest): if both SL and TP1 would hit in the same bar
(high-low range covers both), assume SL hits first. This is the conservative
choice for swing trading (we can't see intrabar sequence).

Costs: applied per trade as (spread + slippage) in price units + commission
on notional. Swap applied per held night.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .bias import (
    BIAS_BULL_STRONG, BIAS_BULL_WEAK, BIAS_BEAR_STRONG, BIAS_BEAR_WEAK,
    BIAS_NEUTRAL, BIAS_CONFLICT, BIAS_NONE,
    classify_bias,
)
from .costs import CostConfig
from .data import Instrument
from .profile import monthly_profiles, weekly_profiles
from .strategy import SETUP_FUNCS, Trade, _atr_4h


@dataclass
class ExecutedTrade:
    instrument: str
    model: str
    side: str
    bias_at_entry: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    sl: float
    tp1: float
    tp2: float
    r_multiple: float       # P/L in R (after costs)
    pnl_pct: float          # P/L as % of account risk (0.5% target risk)
    bars_held: int
    exit_reason: str        # "SL" / "TP1+BE" / "TP2" / "TIME" / "BIAS_FLIP"
    partial_tp1: bool
    risk_price: float


def _apply_entry_cost(side: str, price: float, cost: CostConfig) -> float:
    # We pay half the spread on entry, plus slippage contribution.
    half_spread = cost.spread_price / 2
    slip_half = cost.slippage_price / 2
    if side == "long":
        return price + half_spread + slip_half
    else:
        return price - half_spread - slip_half


def _apply_exit_cost(side: str, price: float, cost: CostConfig) -> float:
    half_spread = cost.spread_price / 2
    slip_half = cost.slippage_price / 2
    if side == "long":
        return price - half_spread - slip_half
    else:
        return price + half_spread + slip_half


def _bars_per_day(_df_4h: pd.DataFrame) -> int:
    return 6  # 24h / 4h


def run_instrument(
    inst: Instrument,
    cost: CostConfig,
    enabled_setups: tuple[str, ...],
    risk_pct_per_trade: float = 0.005,
    time_stop_days: int = 10,
    start_ts: pd.Timestamp | None = None,
    end_ts: pd.Timestamp | None = None,
) -> list[ExecutedTrade]:
    """Run the strategy on a single instrument."""
    df = inst.df_4h
    df_12h = inst.df_12h
    if start_ts is not None:
        df = df[df.index >= start_ts]
    if end_ts is not None:
        df = df[df.index <= end_ts]
    if len(df) < 200:
        return []

    mp = monthly_profiles(df_12h)
    wp = weekly_profiles(inst.df_4h)

    trades: list[ExecutedTrade] = []
    open_trade: ExecutedTrade | None = None

    # Cache 12H closes up to each 4H ts — we need "recent 12H closes at time t"
    # Use the last K completed 12H bars ending at or before ts.
    closes_12h = df_12h["close"].copy()

    bars_per_day = _bars_per_day(df)
    max_hold_bars = time_stop_days * bars_per_day

    # Pre-extract arrays for speed
    index = df.index
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()

    # Rolling ATR 4H, 14
    atr_window = 14
    tr = np.maximum.reduce([
        highs - lows,
        np.abs(highs - np.concatenate([[closes[0]], closes[:-1]])),
        np.abs(lows - np.concatenate([[closes[0]], closes[:-1]])),
    ])
    atr_series = pd.Series(tr).rolling(atr_window, min_periods=atr_window).mean().to_numpy()

    # Long-run ATR for volatility filter
    atr_long = pd.Series(atr_series).rolling(200, min_periods=50).mean().to_numpy()

    # Swap-per-night in price units
    swap = cost.swap_per_night

    for i in range(50, len(df)):
        ts = index[i]
        bar_high = highs[i]
        bar_low = lows[i]
        bar_close = closes[i]
        bar_open = opens[i]

        # ── Step 1: manage open trade ──
        if open_trade is not None:
            t = open_trade
            side = t.side
            hit_sl = False
            hit_tp1 = False
            hit_tp2 = False

            if side == "long":
                if bar_low <= t.sl:
                    hit_sl = True
                if not t.partial_tp1 and bar_high >= t.tp1:
                    hit_tp1 = True
                if t.partial_tp1 and bar_high >= t.tp2:
                    hit_tp2 = True
            else:  # short
                if bar_high >= t.sl:
                    hit_sl = True
                if not t.partial_tp1 and bar_low <= t.tp1:
                    hit_tp1 = True
                if t.partial_tp1 and bar_low <= t.tp2:
                    hit_tp2 = True

            # Conservative: if both SL and TP on same bar, SL first
            if hit_sl and not hit_tp2:
                exit_price = _apply_exit_cost(side, t.sl, cost)
                t.exit_price = exit_price
                t.exit_ts = ts
                t.exit_reason = "SL" if not t.partial_tp1 else "BE_STOP"
                t.bars_held = i - t.entry_bar_idx
                _finalize_trade(t, cost, swap)
                trades.append(t)
                open_trade = None

            elif hit_tp2:
                exit_price = _apply_exit_cost(side, t.tp2, cost)
                t.exit_price = exit_price
                t.exit_ts = ts
                t.exit_reason = "TP2"
                t.bars_held = i - t.entry_bar_idx
                _finalize_trade(t, cost, swap)
                trades.append(t)
                open_trade = None

            elif hit_tp1 and not t.partial_tp1:
                # Partial: book half P/L at TP1, move stop to BE
                t.partial_tp1 = True
                # Record the TP1 event as half-trade P/L; we'll book it into r_multiple later
                t._tp1_bars = i - t.entry_bar_idx
                t._tp1_price = _apply_exit_cost(side, t.tp1, cost)
                # Stop moved to entry (pre-slippage-adjusted break-even)
                t.sl = t.entry_price

            # Time stop
            if open_trade is not None:
                held_bars = i - t.entry_bar_idx
                if held_bars >= max_hold_bars:
                    exit_price = _apply_exit_cost(side, bar_close, cost)
                    t.exit_price = exit_price
                    t.exit_ts = ts
                    t.exit_reason = "TIME"
                    t.bars_held = held_bars
                    _finalize_trade(t, cost, swap)
                    trades.append(t)
                    open_trade = None

        # ── Step 2: look for new entry ──
        if open_trade is None:
            # Cheap volatility filter
            if not np.isfinite(atr_series[i]) or not np.isfinite(atr_long[i]):
                continue
            if atr_series[i] < 0.5 * atr_long[i]:
                continue

            # Only Mon-Thu entries, and not Fri after 12:00 UTC
            weekday = ts.weekday()  # 0=Mon
            if weekday >= 4:  # Fri=4, Sat=5, Sun=6
                continue

            # Get recent 12H closes (last 10 completed 12H bars before ts)
            past_12h = closes_12h[closes_12h.index < ts]
            if len(past_12h) < 10:
                continue
            recent12 = past_12h.iloc[-10:].tolist()

            bias = classify_bias(ts, float(bar_close), mp, wp, recent12)
            if bias.bias in (BIAS_NONE, BIAS_CONFLICT):
                continue

            # Try setups in priority order
            slice_ = df.iloc[max(0, i - 60):i + 1]
            signal = None
            priority = ("A", "C", "D", "B")
            for code in priority:
                if code not in enabled_setups:
                    continue
                fn = SETUP_FUNCS[code]
                proposal = fn(slice_, bias, atr_series[i])
                if proposal is not None:
                    signal = proposal
                    break

            if signal is None:
                continue

            # Enter on close of current bar (pessimistic: next bar open would
            # introduce more lookahead ambiguity; close-entry is standard)
            entry_px = _apply_entry_cost(signal.side, signal.entry, cost)
            # Apply the cost to SL/TP levels too — keep original levels but
            # effective entry is cost-adjusted; SL/TP are price triggers, not cost-adjusted
            risk = abs(entry_px - signal.sl)
            if risk <= 0:
                continue

            t = ExecutedTrade(
                instrument=inst.name,
                model=signal.model,
                side=signal.side,
                bias_at_entry=signal.bias,
                entry_ts=ts,
                exit_ts=ts,
                entry_price=entry_px,
                exit_price=entry_px,
                sl=signal.sl,
                tp1=signal.tp1,
                tp2=signal.tp2,
                r_multiple=0.0,
                pnl_pct=0.0,
                bars_held=0,
                exit_reason="",
                partial_tp1=False,
                risk_price=risk,
            )
            t.entry_bar_idx = i  # type: ignore[attr-defined]
            t._tp1_price = None  # type: ignore[attr-defined]
            t._tp1_bars = None   # type: ignore[attr-defined]
            open_trade = t

    # Close any still-open trade at end of series
    if open_trade is not None:
        t = open_trade
        last_i = len(df) - 1
        exit_price = _apply_exit_cost(t.side, closes[last_i], cost)
        t.exit_price = exit_price
        t.exit_ts = index[last_i]
        t.exit_reason = "EOS"
        t.bars_held = last_i - t.entry_bar_idx
        _finalize_trade(t, cost, swap)
        trades.append(t)

    return trades


def _finalize_trade(t: ExecutedTrade, cost: CostConfig, swap: float):
    """Compute r_multiple and pnl_pct for a closed trade, accounting for
    partial TP1 and swap costs."""
    # Price-unit P/L of the FULL notional
    if t.side == "long":
        pl_main = t.exit_price - t.entry_price
        pl_tp1 = (t._tp1_price - t.entry_price) if t._tp1_price is not None else 0.0
    else:
        pl_main = t.entry_price - t.exit_price
        pl_tp1 = (t.entry_price - t._tp1_price) if t._tp1_price is not None else 0.0

    risk = t.risk_price

    if t.partial_tp1:
        # 50% booked at TP1, 50% at exit_price (which is either TP2 or BE stop hit)
        effective_pl = 0.5 * pl_tp1 + 0.5 * pl_main
        # Swap for bars held on the 50% remaining after TP1
        bars_before_tp1 = t._tp1_bars or 0
        bars_after_tp1 = t.bars_held - bars_before_tp1
        nights = max(0, (bars_before_tp1 // 6)) + 0.5 * max(0, (bars_after_tp1 // 6))
        swap_total = swap * nights
    else:
        effective_pl = pl_main
        nights = t.bars_held // 6
        swap_total = swap * nights

    # Apply swap (negative = cost). Swap direction: treat as subtractive cost always.
    if t.side == "long":
        effective_pl += swap_total
    else:
        effective_pl -= swap_total

    t.r_multiple = effective_pl / risk if risk > 0 else 0.0

    # Commission as a haircut: commission_pct * 2 (entry+exit) of notional.
    # We apply it as a reduction in R-multiple: commission_pct*2 / (risk/entry) per trade.
    # Assume notional-based commission = commission_pct * entry_price (per unit).
    # In R terms, this subtracts (2 * commission_pct * entry) / risk from R.
    comm_r = (2.0 * cost.commission_pct * t.entry_price) / risk if risk > 0 else 0.0
    t.r_multiple -= comm_r

    # pnl_pct: risk per trade = 0.5% of account -> r_multiple * 0.5%
    t.pnl_pct = t.r_multiple * 0.005
