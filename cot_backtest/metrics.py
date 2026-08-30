"""Performance metrics and reporting for the COT weekly backtest.

Account model (per the user's choice):
  * 100,000 USD starting equity
  * 1% of CURRENT equity risked per trade
  * stop sits 1% away from entry, so notional == equity and the P&L of a trade
    in equity terms equals its direction-adjusted price return.

Concurrency note: several instruments can signal in the same week. Each trade
independently risks 1% of equity at the moment it is opened, so a week with 5
simultaneous signals puts 5% at risk. That is the standard reading of "1% risk
per trade" and is reported as such.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

RISK_PER_TRADE = 0.01
START_EQUITY = 100_000.0


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def wilson_ci(k: int, n: int, z: float = 1.96):
    """Wilson score interval for a win rate -- honest for small samples."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def summarize(trades: list) -> dict:
    """Core statistics for a set of trades."""
    n = len(trades)
    if n == 0:
        return {"n": 0}

    rs = [t.r_multiple for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    lo, hi = wilson_ci(len(wins), n)

    se = _stdev(rs) / math.sqrt(n) if n > 1 else 0.0
    mean_r = _mean(rs)
    # Two-sided t-ish statistic on mean R vs 0
    t_stat = mean_r / se if se > 0 else 0.0

    return {
        "n": n,
        "win_rate": len(wins) / n * 100,
        "win_rate_lo": lo * 100,
        "win_rate_hi": hi * 100,
        "wins": len(wins),
        "losses": len(losses),
        "mean_r": mean_r,
        "median_r": _median(rs),
        "stdev_r": _stdev(rs),
        "se_r": se,
        "t_stat": t_stat,
        "total_r": sum(rs),
        "avg_win_r": _mean(wins),
        "avg_loss_r": _mean(losses),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "expectancy_r": mean_r,
        "mean_ret_pct": _mean([t.ret_pct for t in trades]),
        "stop_rate": sum(1 for t in trades if t.exit_reason == "STOP") / n * 100,
        "long_pct": sum(1 for t in trades if t.direction == 1) / n * 100,
        "extreme_pct": sum(1 for t in trades if t.at_extreme) / n * 100,
        "fill_at_open_pct": sum(1 for t in trades if t.filled_at_open) / n * 100,
    }


def equity_curve(trades: list, start: float = START_EQUITY):
    """Compound equity, sizing each trade at 1% risk of equity at entry time.

    Trades are applied in entry-time order. Because positions can overlap, the
    equity used for sizing is the equity as of that trade's entry (realised
    P&L only) -- a deliberately simple and transparent convention.
    """
    ordered = sorted(trades, key=lambda t: t.entry_ts)
    eq = start
    peak = start
    max_dd = 0.0
    curve = [(None, eq)]
    for t in ordered:
        eq += eq * RISK_PER_TRADE * t.r_multiple
        curve.append((t.exit_ts, eq))
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
    return curve, eq, max_dd * 100


def by_key(trades: list, keyfn):
    groups = defaultdict(list)
    for t in trades:
        groups[keyfn(t)].append(t)
    return groups


def fmt_table(rows: list[list[str]], headers: list[str]) -> str:
    all_rows = [headers] + rows
    widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]
    out = []
    out.append("  ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers))))
    out.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for r in rows:
        out.append("  ".join(str(r[i]).ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(out)


def small_sample_flag(n: int) -> str:
    if n < 30:
        return " (!)"
    return ""
