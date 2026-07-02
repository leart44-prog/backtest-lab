"""Stock-selection A/B/C test for the MP-1 swing setups.

Question: does momentum-leadership *selection* add edge, holding setups,
regime filter and costs constant?

Data: S&P 500 daily OHLCV Feb-2013..Feb-2018 (Kaggle mirror via
plotly/datasets on GitHub; Yahoo et al. are blocked by egress policy).

Design:
  - Each month-end, rank all eligible stocks by 121-day return skipping the
    last 5 days (6-month momentum, classic 126-5). Point-in-time: the rank
    computed at month-end M applies throughout month M+1.
  - Quintile Q1 = Leaders, Q3 = Middle, Q5 = Laggards.
  - Run the SAME daily-close swing setups (S1 SMA-reclaim, S2 cup-and-handle,
    S3 EMA-pullback, S5 washout) with REAL volume confirmation on each group.
  - Regime filter from ES futures daily (repo data, resampled 4H->1D).
  - Compare PF / expectancy across groups.

Known biases (documented in report):
  - Survivorship: constituents as of Feb-2018; stocks delisted before then are
    missing. Inflates all groups; the *relative* A/B/C comparison stays valid.
  - Only 5 years, mostly bull regime with 2015-16 chop.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .mp1 import add_indicators, regime_series, RISK_ON, EXTENDED, DEFENSIVE, daily_bars

SCRATCH = "/tmp/claude-0/-home-user-backtest-lab/c7ac16ab-376e-5108-8bd3-d7f3eb3fcfaf/scratchpad"
STOCKS_CSV = os.path.join(SCRATCH, "all_stocks_5yr.csv")

# Round-trip cost assumption for liquid S&P 500 names, in fraction of price:
# ~2-4 bps half-spread + slippage + commission -> 10 bps round trip total.
COST_RT_FRAC = 0.0010


# ─────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────
def load_stocks(min_bars: int = 400) -> dict[str, pd.DataFrame]:
    raw = pd.read_csv(STOCKS_CSV, parse_dates=["date"])
    raw = raw.dropna(subset=["open", "high", "low", "close"])
    out = {}
    for name, g in raw.groupby("Name"):
        if len(g) < min_bars:
            continue
        df = g.set_index("date")[["open", "high", "low", "close", "volume"]].sort_index()
        df.index = df.index.tz_localize("UTC")
        df["vol_avg20"] = df["volume"].rolling(20).mean()
        out[name] = add_indicators(df)
    return out


def momentum_ranks(stocks: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Month-end 126-5 momentum rank -> quintile per ticker per month.

    Returns DataFrame indexed by (month_start, ticker) with column 'quintile'
    (1 = leaders .. 5 = laggards). Rank at month-end M applies in month M+1.
    """
    closes = pd.DataFrame({t: df["close"] for t, df in stocks.items()})
    closes = closes.resample("1D").last()
    mom = closes.shift(5) / closes.shift(126) - 1.0
    month_ends = closes.resample("ME").last().index
    rows = []
    for me in month_ends:
        # last available trading day at or before month end
        upto = mom.loc[:me].dropna(how="all")
        if upto.empty:
            continue
        snap = upto.iloc[-1].dropna()
        if len(snap) < 50:
            continue
        q = pd.qcut(snap.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
        applies_from = (me + pd.Timedelta(days=1)).normalize()
        for ticker, quint in q.items():
            rows.append({"month": applies_from, "ticker": ticker, "quintile": int(quint)})
    return pd.DataFrame(rows)


def quintile_lookup(ranks: pd.DataFrame):
    """dict: (year, month) -> {ticker: quintile}"""
    out = {}
    for month, g in ranks.groupby("month"):
        out[(month.year, month.month)] = dict(zip(g["ticker"], g["quintile"]))
    return out


# ─────────────────────────────────────────────────────────────────────
# Setups — same logic as mp1.py but with real volume confirmation
# ─────────────────────────────────────────────────────────────────────
def _vol_ok(row, mult: float) -> bool:
    va = row.get("vol_avg20")
    return va is not None and not np.isnan(va) and va > 0 and row["volume"] >= mult * va


def detect_s1(df: pd.DataFrame, i: int) -> dict | None:
    if i < 80:
        return None
    row = df.iloc[i]
    if np.isnan(row["sma50"]) or np.isnan(row["atr14"]):
        return None
    if row["sma50_slope"] <= 0:
        return None
    if row["close"] < row["sma50"] * 1.01:
        return None
    if not _vol_ok(row, 1.2):
        return None
    below = df["close"].values[:i] < df["sma50"].values[:i]
    j = i - 1
    recent_above = 0
    while j >= 0 and not below[j]:
        recent_above += 1
        j -= 1
    if recent_above > 2:
        return None
    run = 0
    while j >= 0 and below[j]:
        run += 1
        j -= 1
    if run == 0 or run > 15:
        return None
    stop = row["sma50"] * 0.95
    tp1 = float(df["high"].values[max(0, i - 20):i].max())
    if tp1 <= row["close"]:
        tp1 = row["close"] + 2 * (row["close"] - stop) / 3
    return {"model": "S1", "stop": float(stop), "tp1": float(tp1)}


def detect_s2(df: pd.DataFrame, i: int) -> dict | None:
    if i < 90:
        return None
    row = df.iloc[i]
    if np.isnan(row["sma50"]) or row["close"] < row["sma50"]:
        return None
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
        third = base_high - (base_high - base_low) / 3
        if handle["low"].min() < third:
            continue
        handle_rng = (handle["high"] - handle["low"]).mean()
        if handle_rng >= 0.7 * row["atr20"]:
            continue
        handle_high = handle["high"].max()
        if row["close"] <= handle_high:
            continue
        if not _vol_ok(row, 1.5):
            continue
        stop = float(handle["low"].min() - 0.5 * row["atr14"])
        tp1 = float(row["close"] + (base_high - base_low))
        return {"model": "S2", "stop": stop, "tp1": tp1}
    return None


def detect_s3(df: pd.DataFrame, i: int) -> dict | None:
    if i < 80:
        return None
    row = df.iloc[i]
    if np.isnan(row["ema20"]) or np.isnan(row["atr14"]):
        return None
    if row["close"] < row["sma50"]:
        return None
    last20 = df.iloc[i - 20:i]
    above = (last20["close"] > last20["ema20"]).sum()
    if above < 15:
        return None
    tol = 0.3 * row["atr14"]
    tagged = (row["low"] <= row["ema10"] + tol or row["low"] <= row["ema20"] + tol)
    if not tagged:
        return None
    if row["close"] < row["ema20"]:
        return None
    # pullback-day volume must NOT be a distribution day (vol <= 20d avg)
    va = row.get("vol_avg20")
    if va is None or np.isnan(va) or row["volume"] > va:
        return None
    stop = float(min(row["low"], df.iloc[i - 1]["low"]) - 0.5 * row["atr14"])
    tp1 = float(df["high"].values[max(0, i - 20):i].max())
    if tp1 <= row["close"]:
        return None
    return {"model": "S3", "stop": stop, "tp1": tp1}


def detect_s5(df: pd.DataFrame, i: int) -> dict | None:
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
    rng = row["high"] - row["low"]
    if rng <= 0 or (row["close"] - row["low"]) / rng < 0.66:
        return None
    # capitulation volume on day 3
    if not _vol_ok(row, 1.8):
        return None
    stop = float(row["low"])
    tp1 = float(df.iloc[i - 2]["open"])
    if tp1 <= row["close"]:
        return None
    return {"model": "S5", "stop": stop, "tp1": tp1}


DETECTORS = {"S1": detect_s1, "S2": detect_s2, "S3": detect_s3, "S5": detect_s5}


# ─────────────────────────────────────────────────────────────────────
# Engine (per stock, quintile-gated)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Pos:
    ticker: str
    model: str
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    tp1: float
    risk: float
    frac_open: float = 1.0
    realized_r: float = 0.0
    tp1_done: bool = False
    trim7_done: bool = False
    entry_i: int = 0
    regime_at_entry: str = ""
    quintile: int = 0


def run_stock(
    ticker: str,
    df: pd.DataFrame,
    regime: pd.Series,
    qlookup: dict,
    target_quintiles: set[int],
    enabled: tuple[str, ...] = ("S1", "S2", "S3", "S5"),
) -> list[dict]:
    trades: list[dict] = []
    pos: Pos | None = None
    idx = df.index

    for i in range(130, len(df)):  # 126d momentum warmup
        row = df.iloc[i]
        ts = idx[i]

        # manage
        if pos is not None:
            exited = False
            if row["low"] <= pos.stop:
                r_leg = (pos.stop - pos.entry) / pos.risk
                pos.realized_r += pos.frac_open * r_leg
                trades.append(_close(pos, ts, pos.stop,
                                     "SL" if not pos.tp1_done else "STOP_AFTER_TP1", i))
                pos = None
                exited = True
            if not exited and pos is not None:
                if not pos.tp1_done and row["high"] >= pos.tp1:
                    r_leg = (pos.tp1 - pos.entry) / pos.risk
                    pos.realized_r += (1 / 3) * r_leg
                    pos.frac_open -= 1 / 3
                    pos.tp1_done = True
                    pos.stop = max(pos.stop, pos.entry)
                if not pos.trim7_done and not np.isnan(row["atr50"]) and not np.isnan(row["sma50"]):
                    if row["close"] >= row["sma50"] + 7 * row["atr50"]:
                        r_leg = (row["close"] - pos.entry) / pos.risk
                        pos.realized_r += (1 / 3) * r_leg
                        pos.frac_open -= 1 / 3
                        pos.trim7_done = True
                ema_ref = row["ema10"] if (row["close"] - row["sma50"]) / max(row["atr50"], 1e-12) >= 7 else row["ema20"]
                hard_break = row["close"] < row["sma50"]
                if row["close"] < ema_ref or hard_break:
                    if pos.tp1_done or hard_break:
                        r_leg = (row["close"] - pos.entry) / pos.risk
                        pos.realized_r += pos.frac_open * r_leg
                        trades.append(_close(pos, ts, float(row["close"]),
                                             "SMA50_BREAK" if hard_break else "EMA_TRAIL", i))
                        pos = None

        # entry
        if pos is None:
            q = qlookup.get((ts.year, ts.month), {}).get(ticker)
            if q is None or q not in target_quintiles:
                continue
            reg = regime.reindex([ts]).iloc[0] if ts in regime.index else DEFENSIVE
            if reg == EXTENDED:
                continue
            allowed = enabled if reg == RISK_ON else tuple(s for s in enabled if s in ("S1", "S5"))
            for code in ("S2", "S1", "S3", "S5"):
                if code not in allowed:
                    continue
                sig = DETECTORS[code](df, i)
                if sig is None:
                    continue
                entry = float(row["close"]) * (1 + COST_RT_FRAC)
                stop = sig["stop"]
                if stop >= entry:
                    continue
                risk = entry - stop
                if (sig["tp1"] - entry) / risk < 0.8:
                    continue
                pos = Pos(ticker=ticker, model=sig["model"], entry_ts=ts, entry=entry,
                          stop=stop, tp1=sig["tp1"], risk=risk, entry_i=i,
                          regime_at_entry=reg, quintile=q)
                break

    if pos is not None:
        last = df.iloc[-1]
        r_leg = (float(last["close"]) - pos.entry) / pos.risk
        pos.realized_r += pos.frac_open * r_leg
        trades.append(_close(pos, idx[-1], float(last["close"]), "EOS", len(df) - 1))
    return trades


def _close(pos: Pos, ts, px, reason, i) -> dict:
    return {
        "instrument": pos.ticker, "model": pos.model, "side": "long",
        "bias": pos.regime_at_entry, "quintile": pos.quintile,
        "entry_ts": pos.entry_ts, "exit_ts": ts,
        "entry": pos.entry, "exit": px,
        "r": pos.realized_r, "pnl_pct": pos.realized_r * 0.005,
        "bars": i - pos.entry_i, "reason": reason, "partial_tp1": pos.tp1_done,
    }


def es_regime() -> pd.Series:
    es = add_indicators(daily_bars("ES"))
    return regime_series(es)
