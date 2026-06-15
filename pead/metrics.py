"""Cohort statistics over a list of PEAD trades."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from .signals import Trade


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([asdict(t) for t in trades])


def summary(trades_df: pd.DataFrame) -> dict:
    """Headline cohort stats."""
    if trades_df.empty:
        return {"n_trades": 0}

    r = trades_df["return_pct"].to_numpy()
    wins = r[r > 0]
    losses = r[r <= 0]
    win_rate = float(len(wins) / len(r))
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    profit_factor = float(wins.sum() / -losses.sum()) if losses.sum() != 0 else float("inf")
    expectancy = float(r.mean())
    std = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    sharpe_per_trade = expectancy / std if std > 0 else float("nan")
    avg_hold = float(trades_df["days_held"].mean())
    annualised_trades_per_year = 252.0 / avg_hold if avg_hold > 0 else float("nan")
    sharpe_annualised = sharpe_per_trade * np.sqrt(annualised_trades_per_year) if np.isfinite(sharpe_per_trade) else float("nan")

    exit_counts = trades_df["exit_reason"].value_counts().to_dict()

    return {
        "n_trades": int(len(r)),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "sharpe_per_trade": sharpe_per_trade,
        "sharpe_annualised": sharpe_annualised,
        "avg_hold_days": avg_hold,
        "median_mae": float(trades_df["mae_pct"].median()),
        "median_mfe": float(trades_df["mfe_pct"].median()),
        "exit_reasons": exit_counts,
    }


def stratify_by_gap(trades_df: pd.DataFrame, buckets: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20, 1.0)) -> pd.DataFrame:
    """Split trades by gap-size bucket; report mean return + win rate per bucket."""
    if trades_df.empty:
        return pd.DataFrame()
    labels = []
    for lo, hi in zip(buckets[:-1], buckets[1:]):
        labels.append(f"{int(lo*100)}-{int(hi*100)}%" if hi < 1.0 else f">={int(lo*100)}%")
    cat = pd.cut(trades_df["gap_pct"], bins=list(buckets), labels=labels, include_lowest=True, right=False)
    grouped = trades_df.assign(bucket=cat).groupby("bucket", observed=True).agg(
        n=("return_pct", "size"),
        mean_return=("return_pct", "mean"),
        median_return=("return_pct", "median"),
        win_rate=("return_pct", lambda s: float((s > 0).mean())),
        avg_hold=("days_held", "mean"),
    )
    return grouped


def equity_curve(trades_df: pd.DataFrame, capital: float = 100_000.0, position_frac: float = 0.05) -> pd.Series:
    """Compounded equity assuming `position_frac` of equity allocated per trade.

    Trades are processed in chronological entry order. Simplification: ignores
    concurrent trades (one trade at a time on the books).
    """
    if trades_df.empty:
        return pd.Series(dtype=float)
    df = trades_df.sort_values("entry_date").reset_index(drop=True)
    eq = capital
    points = [(df["entry_date"].iloc[0], eq)]
    for _, row in df.iterrows():
        pnl = eq * position_frac * row["return_pct"]
        eq += pnl
        points.append((row["exit_date"], eq))
    return pd.Series([p[1] for p in points], index=[p[0] for p in points], name="equity")
