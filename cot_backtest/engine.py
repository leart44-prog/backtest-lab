"""
COT Non-Commercial weekly directional backtest.

Strategy (as specified by the user, no parameters fitted to performance):
  * Weekly CFTC COT report (Legacy, Futures-only), Non-Commercial positions.
  * net           = NonComm Long - NonComm Short
  * net_change    = net[w] - net[w-1]
  * COT Index     = Williams %-rank of net over a trailing lookback window.
  * Trade only "significant" net changes: |net_change| > k * stdev(net_change, trailing).
  * Not at an extreme  -> follow the non-commercials: direction = sign(net_change)
  * At an extreme      -> take the opposite signal: direction = -sign(net_change)
  * Entry: at the following market open, LIMIT order at the gap-fill level
           (= previous Friday's close). Marketable limits fill at the open.
  * Stop:  1% adverse price move from entry.
  * Exit:  open of the next weekly session (i.e. when the next COT report cycle
           has been released), or the stop, whichever comes first.

POINT-IN-TIME RULE (the core correctness constraint)
----------------------------------------------------
A COT bar stamped Monday 00:00 UTC of week W describes positions as of
*Tuesday of week W* and is only PUBLISHED on *Friday of week W, 15:30 ET*.
Trading it during week W would be a 5-day look-ahead. The engine therefore
requires the entry week to OPEN strictly after the release instant.
"""

from __future__ import annotations

import gzip
import json
import math
import os
from dataclasses import dataclass, asdict, field

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PRICE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

WEEK = 604800
DAY = 86400

# Tick sizes (1 tick slippage is charged on entry and on exit).
FUTURES_TICK = {
    "ES": 0.25, "NQ": 0.25, "YM": 1.0, "RTY": 0.1, "NKD": 5.0, "DAX": 0.5,
    "CL": 0.01, "NG": 0.001, "GC": 0.1, "SI": 0.005, "HG": 0.0005,
    "PA": 0.05, "PL": 0.1,
    "ZC": 0.25, "ZS": 0.25, "ZW": 0.25, "ZO": 0.25,
    "CC": 1.0, "CT": 0.01, "OJ": 0.05, "SB": 0.01, "KC": 0.05,
    "6A": 0.0001, "6B": 0.0001, "6C": 0.0001, "6E": 0.0001,
    "6J": 0.000001, "6N": 0.0001, "6S": 0.0001,
}

ASSET_CLASS = {
    "6A": "FX", "6B": "FX", "6C": "FX", "6E": "FX", "6J": "FX", "6N": "FX", "6S": "FX",
    "ES": "Index", "NQ": "Index", "RTY": "Index", "YM": "Index",
    "SI": "Metals", "HG": "Metals", "PL": "Metals", "PA": "Metals", "GC": "Metals",
    "CL": "Energy", "NG": "Energy",
    "ZC": "Grains", "ZS": "Grains", "ZW": "Grains", "ZO": "Grains",
    "SB": "Softs", "CC": "Softs", "CT": "Softs", "OJ": "Softs", "KC": "Softs",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_cot(symbol: str) -> dict:
    """Load the non-commercial long/short weekly series for one instrument.

    Returns dict with 'ts' (report-week Monday 00:00 UTC) and 'net'.
    """
    with open(os.path.join(DATA_DIR, "cot", f"{symbol}_L.json")) as fh:
        lo = json.load(fh)
    with open(os.path.join(DATA_DIR, "cot", f"{symbol}_S.json")) as fh:
        sh = json.load(fh)

    if lo["first_t"] != sh["first_t"] or len(lo["closes"]) != len(sh["closes"]):
        raise ValueError(f"{symbol}: long/short COT series are not aligned")

    n = len(lo["closes"])
    ts = [lo["first_t"] + i * lo["step"] for i in range(n)]
    net = [lo["closes"][i] - sh["closes"][i] for i in range(n)]
    return {"ts": ts, "net": net, "long": lo["closes"], "short": sh["closes"]}


@dataclass
class Week:
    """One contiguous weekly trading session built from 4H bars."""
    open_ts: int
    close_ts: int
    open_px: float
    close_px: float
    bars: list  # [[ts, o, h, l, c], ...] in chronological order


def load_price_weeks(symbol: str) -> list[Week]:
    """Load 4H bars and group them into weekly sessions.

    Week boundaries are detected from the weekend gap (>24h between bars)
    rather than from fixed clock times, so US daylight-saving shifts in the
    session open do not corrupt the grouping.
    """
    path = os.path.join(PRICE_DIR, f"{symbol}.json.gz")
    with gzip.open(path) as fh:
        raw = json.load(fh)

    raw.sort(key=lambda r: r[0])
    # Drop exact duplicate timestamps, keeping the first occurrence.
    deduped = []
    seen = set()
    for r in raw:
        if r[0] in seen:
            continue
        seen.add(r[0])
        deduped.append(r)

    weeks: list[Week] = []
    cur: list = []
    for i, bar in enumerate(deduped):
        if cur and (bar[0] - cur[-1][0]) > 24 * 3600:
            weeks.append(_mk_week(cur))
            cur = []
        cur.append(bar)
    if cur:
        weeks.append(_mk_week(cur))
    return weeks


def _mk_week(bars: list) -> Week:
    return Week(
        open_ts=bars[0][0],
        close_ts=bars[-1][0],
        open_px=bars[0][1],
        close_px=bars[-1][4],
        bars=bars,
    )


# ---------------------------------------------------------------------------
# Signal construction (all trailing / causal)
# ---------------------------------------------------------------------------

def cot_index(net: list[float], i: int, lookback: int) -> float | None:
    """Williams COT Index at week i, using only weeks <= i."""
    lo_i = i - lookback + 1
    if lo_i < 0:
        return None
    window = net[lo_i:i + 1]
    mn, mx = min(window), max(window)
    if mx == mn:
        return 50.0
    return (net[i] - mn) / (mx - mn) * 100.0


def rolling_std(vals: list[float], i: int, lookback: int) -> float | None:
    """Sample stdev of vals[i-lookback+1 .. i], using only weeks <= i."""
    lo_i = i - lookback + 1
    if lo_i < 0:
        return None
    w = vals[lo_i:i + 1]
    if len(w) < 2:
        return None
    m = sum(w) / len(w)
    var = sum((x - m) ** 2 for x in w) / (len(w) - 1)
    return math.sqrt(var)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    symbol: str
    asset_class: str
    report_week_ts: int       # COT report week (Monday 00:00 UTC)
    release_ts: int           # when the report became public
    entry_week_open_ts: int
    entry_ts: int
    exit_ts: int
    direction: int            # +1 long, -1 short
    at_extreme: bool
    cot_index: float
    net_change: float
    net_change_sigma: float   # |net_change| / trailing stdev
    limit_px: float
    week_open_px: float
    gap_pct: float
    filled_at_open: bool
    entry_px: float
    stop_px: float
    exit_px: float
    exit_reason: str          # 'STOP' | 'TIME'
    ret_pct: float            # direction-adjusted, after slippage
    r_multiple: float
    year: int
    bars_held: int


# Release: Friday 15:30 ET of the report week. The COT bar is stamped Monday
# 00:00 UTC, so the release is ~4 days + 20.5h later. We use a conservative
# 5-day offset, which lands on the Saturday and therefore always excludes the
# report week's own trading session.
RELEASE_OFFSET = 5 * DAY


def run_symbol(
    symbol: str,
    sigma_k: float,
    extreme_hi: float = 80.0,
    extreme_lo: float = 20.0,
    cot_lookback: int = 156,
    sig_lookback: int = 52,
    stop_pct: float = 0.01,
    slippage_ticks: float = 1.0,
    contrarian_at_extreme: bool = True,
) -> list[Trade]:
    """Run the strategy for one instrument and return its trades."""
    cot = load_cot(symbol)
    weeks = load_price_weeks(symbol)
    if not weeks:
        return []

    net = cot["net"]
    ts = cot["ts"]
    net_chg = [0.0] + [net[i] - net[i - 1] for i in range(1, len(net))]

    tick = FUTURES_TICK.get(symbol, 0.0)
    slip = tick * slippage_ticks

    week_opens = [w.open_ts for w in weeks]
    trades: list[Trade] = []

    for i in range(len(net)):
        idx = cot_index(net, i, cot_lookback)
        sd = rolling_std(net_chg, i, sig_lookback)
        if idx is None or sd is None or sd <= 0:
            continue
        if net_chg[i] == 0:
            continue

        sigma = abs(net_chg[i]) / sd
        if sigma <= sigma_k:
            continue  # not a "significant" change

        base_dir = 1 if net_chg[i] > 0 else -1
        at_extreme = idx > extreme_hi or idx < extreme_lo
        direction = -base_dir if (at_extreme and contrarian_at_extreme) else base_dir

        release_ts = ts[i] + RELEASE_OFFSET

        # --- Point-in-time gate: entry week must OPEN after the release ---
        e = _first_week_after(week_opens, release_ts)
        if e is None or e == 0 or e + 1 >= len(weeks):
            continue

        entry_week = weeks[e]
        prev_week = weeks[e - 1]
        exit_week = weeks[e + 1]

        # Guard against data holes: the previous session must be the one
        # immediately preceding the entry week (< 10 days apart).
        if entry_week.open_ts - prev_week.close_ts > 10 * DAY:
            continue

        limit_px = prev_week.close_px  # the gap-fill level
        if limit_px <= 0:
            continue
        gap_pct = (entry_week.open_px - limit_px) / limit_px * 100.0

        fill = _fill_limit(entry_week, limit_px, direction)
        if fill is None:
            continue
        fill_bar_i, raw_entry, filled_at_open = fill

        entry_px = raw_entry + slip * direction  # slippage against us
        if entry_px <= 0:
            continue
        stop_px = entry_px * (1 - stop_pct) if direction == 1 else entry_px * (1 + stop_pct)

        exit_px, exit_ts, reason, bars_held = _manage(
            entry_week, exit_week, fill_bar_i, stop_px, direction
        )
        exit_px_eff = exit_px - slip * direction  # slippage against us

        ret = (exit_px_eff - entry_px) / entry_px * direction

        trades.append(Trade(
            symbol=symbol,
            asset_class=ASSET_CLASS.get(symbol, "?"),
            report_week_ts=ts[i],
            release_ts=release_ts,
            entry_week_open_ts=entry_week.open_ts,
            entry_ts=entry_week.bars[fill_bar_i][0],
            exit_ts=exit_ts,
            direction=direction,
            at_extreme=at_extreme,
            cot_index=round(idx, 2),
            net_change=net_chg[i],
            net_change_sigma=round(sigma, 3),
            limit_px=limit_px,
            week_open_px=entry_week.open_px,
            gap_pct=round(gap_pct, 4),
            filled_at_open=filled_at_open,
            entry_px=entry_px,
            stop_px=stop_px,
            exit_px=exit_px_eff,
            exit_reason=reason,
            ret_pct=ret * 100.0,
            r_multiple=ret / stop_pct,
            year=_year_of(entry_week.open_ts),
            bars_held=bars_held,
        ))

    return trades


def _first_week_after(week_opens: list[int], t: int) -> int | None:
    """Index of the first weekly session opening strictly after t."""
    lo, hi = 0, len(week_opens)
    while lo < hi:
        mid = (lo + hi) // 2
        if week_opens[mid] > t:
            hi = mid
        else:
            lo = mid + 1
    return lo if lo < len(week_opens) else None


def _fill_limit(week: Week, limit: float, direction: int):
    """Try to fill a limit order at `limit` during `week`.

    Returns (bar_index, fill_price, filled_at_open) or None.
    A marketable limit (market already through the limit at the open) fills at
    the open, which is the better price -- exactly how a real limit behaves.
    """
    o = week.open_px
    if direction == 1:
        if o <= limit:
            return 0, o, True
        for j, b in enumerate(week.bars):
            if b[3] <= limit:  # low
                return j, limit, False
    else:
        if o >= limit:
            return 0, o, True
        for j, b in enumerate(week.bars):
            if b[2] >= limit:  # high
                return j, limit, False
    return None


def _manage(entry_week: Week, exit_week: Week, fill_bar_i: int,
            stop_px: float, direction: int):
    """Walk forward from the fill bar; stop out or exit at next week's open.

    The fill bar itself is included in the stop scan. Within a single 4H bar we
    cannot know whether the limit or the stop printed first, so we assume the
    adverse case. This biases results DOWN, never up.
    """
    held = 0
    for j in range(fill_bar_i, len(entry_week.bars)):
        b = entry_week.bars[j]
        held += 1
        if direction == 1 and b[3] <= stop_px:
            return stop_px, b[0], "STOP", held
        if direction == -1 and b[2] >= stop_px:
            return stop_px, b[0], "STOP", held
    return exit_week.open_px, exit_week.open_ts, "TIME", held


def _year_of(ts: int) -> int:
    import datetime as dt
    return dt.datetime.utcfromtimestamp(ts).year
