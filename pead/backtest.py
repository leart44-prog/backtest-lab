"""Cross-sectional PEAD backtest over a universe."""

from __future__ import annotations

import pandas as pd

from .signals import run_ticker, Trade


def run_universe(
    data: dict[str, pd.DataFrame],
    gap_pct: float = 0.05,
    max_days: int = 60,
) -> list[Trade]:
    """Run PEAD detection + simulation across every ticker in `data`."""
    all_trades: list[Trade] = []
    for ticker, df in data.items():
        try:
            trades = run_ticker(ticker, df, gap_pct=gap_pct, max_days=max_days)
            all_trades.extend(trades)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {ticker} skipped: {exc}")
    return all_trades
