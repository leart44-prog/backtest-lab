"""Analytics: metrics, equity curve, Monte Carlo.

All calculations operate on lists of ExecutedTrade (across instruments,
sorted by entry_ts). P/L measured in R-multiples and in % of equity.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import ExecutedTrade


@dataclass
class Metrics:
    n_trades: int
    n_wins: int
    n_losses: int
    win_rate: float
    avg_r: float
    avg_win_r: float
    avg_loss_r: float
    profit_factor: float
    expectancy_r: float
    sum_r: float
    max_dd_r: float
    max_dd_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    longest_loss_streak: int
    longest_win_streak: int
    avg_hold_bars: float


def trades_to_df(trades: list[ExecutedTrade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    rows = []
    for t in trades:
        rows.append({
            "instrument": t.instrument, "model": t.model, "side": t.side,
            "bias": t.bias_at_entry,
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
            "entry": t.entry_price, "exit": t.exit_price,
            "r": t.r_multiple, "pnl_pct": t.pnl_pct,
            "bars": t.bars_held, "reason": t.exit_reason,
            "partial_tp1": t.partial_tp1,
        })
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def equity_curve(df_trades: pd.DataFrame, start_equity: float = 100_000.0,
                 risk_pct: float = 0.005) -> pd.DataFrame:
    """Compound equity curve. Each trade risks `risk_pct` × current equity.
    Bar-time equity plotted at trade exit."""
    if df_trades.empty:
        return pd.DataFrame({"ts": [], "equity": []})
    eq = start_equity
    out = []
    for _, r in df_trades.iterrows():
        pnl = r["r"] * risk_pct * eq
        eq = eq + pnl
        out.append({"ts": r["exit_ts"], "equity": eq})
    return pd.DataFrame(out)


def drawdown_series(eq_df: pd.DataFrame) -> pd.DataFrame:
    if eq_df.empty:
        return pd.DataFrame({"ts": [], "dd_pct": []})
    eq = eq_df["equity"].values
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak * 100
    return pd.DataFrame({"ts": eq_df["ts"].values, "dd_pct": dd})


def compute_metrics(df_trades: pd.DataFrame, start_equity: float = 100_000.0,
                    risk_pct: float = 0.005) -> Metrics:
    if df_trades.empty:
        return Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    r = df_trades["r"].values
    wins_mask = r > 0
    losses_mask = r <= 0
    n = len(r)
    n_wins = int(wins_mask.sum())
    n_losses = int(losses_mask.sum())
    win_rate = n_wins / n if n > 0 else 0.0
    avg_win_r = float(r[wins_mask].mean()) if n_wins > 0 else 0.0
    avg_loss_r = float(r[losses_mask].mean()) if n_losses > 0 else 0.0
    sum_win = float(r[wins_mask].sum())
    sum_loss = float(-r[losses_mask].sum())
    profit_factor = (sum_win / sum_loss) if sum_loss > 0 else (float("inf") if sum_win > 0 else 0.0)
    expectancy_r = float(r.mean()) if n > 0 else 0.0
    sum_r = float(r.sum())

    # Equity curve
    eq = equity_curve(df_trades, start_equity, risk_pct)
    dd = drawdown_series(eq)
    max_dd_pct = float(abs(dd["dd_pct"].min())) if not dd.empty else 0.0

    # Max DD in R
    cum_r = np.cumsum(r)
    peak_r = np.maximum.accumulate(cum_r)
    max_dd_r = float((cum_r - peak_r).min()) if n > 0 else 0.0

    # CAGR
    if not eq.empty:
        years = max((eq["ts"].iloc[-1] - df_trades["entry_ts"].iloc[0]).days / 365.25, 0.01)
        final_eq = float(eq["equity"].iloc[-1])
        cagr_pct = ((final_eq / start_equity) ** (1 / years) - 1) * 100
    else:
        cagr_pct = 0.0

    # Sharpe / Sortino (trade-level)
    pnl_pct = df_trades["pnl_pct"].values
    if len(pnl_pct) > 1 and np.std(pnl_pct) > 0:
        sharpe = float(np.mean(pnl_pct) / np.std(pnl_pct) * np.sqrt(52))  # trades ≈ weekly-ish
        downside = pnl_pct[pnl_pct < 0]
        sortino = float(np.mean(pnl_pct) / np.std(downside) * np.sqrt(52)) if len(downside) > 1 and np.std(downside) > 0 else 0.0
    else:
        sharpe = sortino = 0.0

    # Streaks
    wins_bool = (r > 0).astype(int)
    losses_bool = (r <= 0).astype(int)
    longest_win = _longest_streak(wins_bool)
    longest_loss = _longest_streak(losses_bool)

    avg_hold = float(df_trades["bars"].mean())

    return Metrics(
        n_trades=n,
        n_wins=n_wins,
        n_losses=n_losses,
        win_rate=win_rate,
        avg_r=expectancy_r,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        profit_factor=profit_factor,
        expectancy_r=expectancy_r,
        sum_r=sum_r,
        max_dd_r=max_dd_r,
        max_dd_pct=max_dd_pct,
        cagr_pct=cagr_pct,
        sharpe=sharpe,
        sortino=sortino,
        longest_loss_streak=longest_loss,
        longest_win_streak=longest_win,
        avg_hold_bars=avg_hold,
    )


def _longest_streak(arr: np.ndarray) -> int:
    best = cur = 0
    for v in arr:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def monte_carlo(
    r_series: np.ndarray,
    n_runs: int = 1000,
    start_equity: float = 100_000.0,
    risk_pct: float = 0.005,
    seed: int = 42,
) -> dict:
    """Bootstrap: resample trade R-multiples with replacement, compute DD stats."""
    rng = np.random.default_rng(seed)
    n = len(r_series)
    if n == 0:
        return {}
    end_eq = np.zeros(n_runs)
    max_dd_pct = np.zeros(n_runs)
    max_loss_streak = np.zeros(n_runs, dtype=int)

    for k in range(n_runs):
        shuffled = rng.choice(r_series, size=n, replace=True)
        eq = np.full(n + 1, start_equity)
        cur = start_equity
        for j, r in enumerate(shuffled):
            cur += r * risk_pct * cur
            eq[j + 1] = cur
        end_eq[k] = cur
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / peak * 100
        max_dd_pct[k] = abs(dd.min())
        # longest losing streak
        losses = (shuffled <= 0).astype(int)
        max_loss_streak[k] = _longest_streak(losses)

    return {
        "n_runs": n_runs,
        "median_final_equity": float(np.median(end_eq)),
        "p5_final_equity": float(np.percentile(end_eq, 5)),
        "p95_final_equity": float(np.percentile(end_eq, 95)),
        "median_dd_pct": float(np.median(max_dd_pct)),
        "p95_dd_pct": float(np.percentile(max_dd_pct, 95)),
        "p99_dd_pct": float(np.percentile(max_dd_pct, 99)),
        "p_dd_gt_10": float(np.mean(max_dd_pct > 10)),
        "p_dd_gt_20": float(np.mean(max_dd_pct > 20)),
        "p_dd_gt_30": float(np.mean(max_dd_pct > 30)),
        "median_max_loss_streak": float(np.median(max_loss_streak)),
        "p95_max_loss_streak": float(np.percentile(max_loss_streak, 95)),
        "p_loss_streak_ge_10": float(np.mean(max_loss_streak >= 10)),
        "p_loss_streak_ge_15": float(np.mean(max_loss_streak >= 15)),
    }


def split_in_out_sample(df_trades: pd.DataFrame, split_ts: pd.Timestamp):
    ins = df_trades[df_trades["entry_ts"] < split_ts].copy()
    oos = df_trades[df_trades["entry_ts"] >= split_ts].copy()
    return ins, oos


def metrics_by_group(df_trades: pd.DataFrame, groupby: str,
                     start_equity: float = 100_000.0) -> pd.DataFrame:
    """Compute key metrics per group (instrument / model / year / weekday)."""
    rows = []
    if df_trades.empty:
        return pd.DataFrame()
    for key, grp in df_trades.groupby(groupby):
        m = compute_metrics(grp, start_equity=start_equity)
        rows.append({
            groupby: key,
            "n": m.n_trades,
            "win_rate": m.win_rate,
            "avg_r": m.avg_r,
            "pf": m.profit_factor if np.isfinite(m.profit_factor) else np.nan,
            "sum_r": m.sum_r,
            "max_dd_pct": m.max_dd_pct,
            "cagr_pct": m.cagr_pct,
        })
    return pd.DataFrame(rows).sort_values("sum_r", ascending=False)
