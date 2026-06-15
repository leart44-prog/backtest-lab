"""CLI: fetch S&P 100 (or use synthetic data) -> detect gap events -> simulate trades -> report.

Examples
--------
Verification (offline, planted edge):
    uv run python -m pead.run --synthetic

Real data (needs Yahoo reachable):
    uv run python -m pead.run --years 10 --gap-pct 0.05

Single ticker:
    uv run python -m pead.run --tickers MU,NVDA,AVGO --years 5
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from .backtest import run_universe
from .metrics import summary, stratify_by_gap, trades_to_frame, equity_curve
from .universe import SP100


def _print_summary(s: dict, label: str) -> None:
    print(f"\n{label}")
    print("-" * len(label))
    if s.get("n_trades", 0) == 0:
        print("  no trades")
        return
    print(f"  n_trades:           {s['n_trades']}")
    print(f"  win_rate:           {s['win_rate']*100:.2f}%")
    print(f"  avg_win:            {s['avg_win']*100:+.2f}%")
    print(f"  avg_loss:           {s['avg_loss']*100:+.2f}%")
    print(f"  profit_factor:      {s['profit_factor']:.2f}")
    print(f"  expectancy/trade:   {s['expectancy']*100:+.2f}%")
    print(f"  sharpe_per_trade:   {s['sharpe_per_trade']:.3f}")
    print(f"  sharpe_annualised:  {s['sharpe_annualised']:.3f}")
    print(f"  avg_hold_days:      {s['avg_hold_days']:.1f}")
    print(f"  median_MAE:         {s['median_mae']*100:+.2f}%")
    print(f"  median_MFE:         {s['median_mfe']*100:+.2f}%")
    print(f"  exit_reasons:       {s['exit_reasons']}")


def main() -> int:
    p = argparse.ArgumentParser(prog="pead")
    p.add_argument("--tickers", default=None, help="Comma list; default = S&P 100")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--gap-pct", type=float, default=0.05)
    p.add_argument("--max-days", type=int, default=60)
    p.add_argument("--synthetic", action="store_true", help="Use planted synthetic data instead of yfinance")
    p.add_argument("--null", action="store_true", help="With --synthetic: zero planted drift (null hypothesis)")
    p.add_argument("--out", default=None, help="Optional CSV path for the trades table")
    args = p.parse_args()

    if args.synthetic:
        from .synthetic import make_universe
        drift = 0.0 if args.null else 0.07
        print(f"Building 100 synthetic tickers (planted 60d drift = {drift*100:.1f}%)...")
        data = make_universe(n=100, drift_60d=drift)
    else:
        from .fetch import fetch_universe
        tickers = args.tickers.split(",") if args.tickers else SP100
        print(f"Fetching {len(tickers)} tickers, {args.years}y daily...")
        data = fetch_universe(tickers, years=args.years)
        if not data:
            print("\nNo data fetched. Yahoo likely unreachable.")
            print("Run with --synthetic to verify the logic.")
            return 2

    print(f"\nDetecting gap events (>= {args.gap_pct*100:.1f}%) and simulating trades...")
    trades = run_universe(data, gap_pct=args.gap_pct, max_days=args.max_days)
    df = trades_to_frame(trades)
    print(f"  {len(df)} trades across {df['ticker'].nunique() if not df.empty else 0} tickers")

    _print_summary(summary(df), "PEAD cohort — headline")
    print("\nStratified by gap size:")
    print(stratify_by_gap(df).round(4).to_string())

    eq = equity_curve(df, capital=100_000.0, position_frac=0.05)
    if not eq.empty:
        ret = eq.iloc[-1] / eq.iloc[0] - 1
        print(f"\nEquity (5% per trade, sequential): ${eq.iloc[0]:,.0f} -> ${eq.iloc[-1]:,.0f}  ({ret*100:+.2f}% total)")

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"\nTrades written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
