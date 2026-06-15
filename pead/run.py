"""CLI: fetch S&P 100 (or use synthetic data) -> detect gap events -> simulate trades -> report.

Examples
--------
Earnings PEAD on synthetic data:
    uv run python -m pead.run --synthetic

News-gap variant on synthetic data:
    uv run python -m pead.run --synthetic --mode news

Side-by-side comparison (earnings vs news on their respective profiles):
    uv run python -m pead.run --synthetic --compare

Real data (needs Yahoo reachable):
    uv run python -m pead.run --years 10 --mode earnings
    uv run python -m pead.run --years 10 --mode news
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from .backtest import run_universe
from .metrics import equity_curve, stratify_by_gap, summary, trades_to_frame
from .news_gap import run_universe_news
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


def _print_comparison(s_e: dict, s_n: dict) -> None:
    rows = [
        ("Anzahl Trades",          f"{s_e.get('n_trades', 0)}",                  f"{s_n.get('n_trades', 0)}"),
        ("Win Rate",               f"{s_e.get('win_rate', 0)*100:.2f}%",         f"{s_n.get('win_rate', 0)*100:.2f}%"),
        ("Profit Factor",          f"{s_e.get('profit_factor', 0):.2f}",         f"{s_n.get('profit_factor', 0):.2f}"),
        ("Expectancy / Trade",     f"+{s_e.get('expectancy', 0)*100:.2f}%",      f"+{s_n.get('expectancy', 0)*100:.2f}%"),
        ("Avg Win",                f"+{s_e.get('avg_win', 0)*100:.2f}%",         f"+{s_n.get('avg_win', 0)*100:.2f}%"),
        ("Avg Loss",               f"{s_e.get('avg_loss', 0)*100:+.2f}%",        f"{s_n.get('avg_loss', 0)*100:+.2f}%"),
        ("Sharpe (annualisiert)",  f"{s_e.get('sharpe_annualised', 0):.2f}",     f"{s_n.get('sharpe_annualised', 0):.2f}"),
        ("Avg Hold (Tage)",        f"{s_e.get('avg_hold_days', 0):.1f}",         f"{s_n.get('avg_hold_days', 0):.1f}"),
        ("Median MAE",             f"{s_e.get('median_mae', 0)*100:+.2f}%",      f"{s_n.get('median_mae', 0)*100:+.2f}%"),
        ("Median MFE",             f"{s_e.get('median_mfe', 0)*100:+.2f}%",      f"{s_n.get('median_mfe', 0)*100:+.2f}%"),
    ]
    print("\nCohort comparison")
    print("-" * 17)
    print(f"  {'Metrik':<24s} {'Earnings':>14s} {'News-Gap':>14s}")
    print(f"  {'-'*24} {'-'*14} {'-'*14}")
    for label, e, n in rows:
        print(f"  {label:<24s} {e:>14s} {n:>14s}")


def _run_mode(data, mode: str, gap_pct: float, max_days: int, vol_mult: float):
    if mode == "earnings":
        print(f"\n[earnings] Detecting gap events (>= {gap_pct*100:.1f}%) and simulating trades...")
        trades = run_universe(data, gap_pct=gap_pct, max_days=max_days)
    else:
        print(f"\n[news-gap] Detecting gaps (>= {gap_pct*100:.1f}%) with volume >= {vol_mult:.1f}x avg...")
        trades = run_universe_news(data, gap_pct=gap_pct, vol_mult=vol_mult, max_days=max_days)
    df = trades_to_frame(trades)
    print(f"  {len(df)} trades across {df['ticker'].nunique() if not df.empty else 0} tickers")
    return df


def main() -> int:
    p = argparse.ArgumentParser(prog="pead")
    p.add_argument("--mode", choices=["earnings", "news"], default="earnings",
                   help="earnings: classic PEAD setup; news: tighter stop, faster trail, shorter hold")
    p.add_argument("--compare", action="store_true",
                   help="Run both modes on their respective synthetic profiles and print side-by-side")
    p.add_argument("--tickers", default=None, help="Comma list; default = S&P 100")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--gap-pct", type=float, default=None, help="Default 0.05 (earnings) or 0.08 (news)")
    p.add_argument("--vol-mult", type=float, default=3.0, help="News-mode volume multiplier")
    p.add_argument("--max-days", type=int, default=None, help="Default 60 (earnings) or 25 (news)")
    p.add_argument("--synthetic", action="store_true", help="Use planted synthetic data instead of yfinance")
    p.add_argument("--null", action="store_true", help="With --synthetic: zero planted drift")
    p.add_argument("--out", default=None, help="Optional CSV path for the trades table")
    args = p.parse_args()

    if args.compare:
        if not args.synthetic:
            print("--compare requires --synthetic (real data would need separate fetches per profile).")
            return 2
        from .synthetic import make_universe
        print("Building earnings universe (planted 60d drift = +7%)...")
        data_e = make_universe(n=100, profile="earnings")
        print("Building news universe (planted 20d drift = +4%, 30% mean-revert)...")
        data_n = make_universe(n=100, profile="news")

        df_e = _run_mode(data_e, "earnings", 0.05, 60, args.vol_mult)
        df_n = _run_mode(data_n, "news", 0.08, 25, args.vol_mult)

        s_e = summary(df_e)
        s_n = summary(df_n)
        _print_summary(s_e, "Earnings PEAD")
        _print_summary(s_n, "News-Gap variant")
        _print_comparison(s_e, s_n)
        return 0

    gap_default = 0.05 if args.mode == "earnings" else 0.08
    days_default = 60 if args.mode == "earnings" else 25
    gap_pct = args.gap_pct if args.gap_pct is not None else gap_default
    max_days = args.max_days if args.max_days is not None else days_default

    if args.synthetic:
        from .synthetic import make_universe
        profile = args.mode if not args.null else "earnings"
        kwargs = {"event_drift_mean": 0.0} if args.null else {}
        print(f"Building 100 synthetic tickers (profile={profile}{', null' if args.null else ''})...")
        data = make_universe(n=100, profile=profile, **kwargs)
    else:
        from .fetch import fetch_universe
        tickers = args.tickers.split(",") if args.tickers else SP100
        print(f"Fetching {len(tickers)} tickers, {args.years}y daily...")
        data = fetch_universe(tickers, years=args.years)
        if not data:
            print("\nNo data fetched. Yahoo likely unreachable.")
            print("Run with --synthetic to verify the logic.")
            return 2

    df = _run_mode(data, args.mode, gap_pct, max_days, args.vol_mult)
    label = "PEAD cohort — earnings" if args.mode == "earnings" else "PEAD cohort — news-gap"
    _print_summary(summary(df), label)

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
