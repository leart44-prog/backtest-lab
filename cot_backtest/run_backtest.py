"""Run the COT weekly directional backtest and print the report."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys
from dataclasses import asdict

import engine
import metrics as M

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(OUT_DIR, exist_ok=True)

# Universe: every instrument for which BOTH a CFTC COT series and local 4H
# price history exist. Fixed before any result was looked at.
UNIVERSE = [s for s in ("6A", "6E", "6J", "6B", "ES", "NQ", "CL", "SI", "ZC", "SB")
            if os.path.exists(os.path.join(engine.DATA_DIR, "cot", f"{s}_L.json"))]

# Pre-registered grid. Reported in full -- the point is the shape of the
# curve, not the maximum.
SIGMA_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

# Out-of-sample split: first ~70% of calendar time is IS, remainder is OOS.
OOS_START_YEAR = 2023


def ts(x):
    return dt.datetime.utcfromtimestamp(x).strftime("%Y-%m-%d")


def collect(sigma_k: float, contrarian: bool = True) -> list:
    out = []
    for sym in UNIVERSE:
        out.extend(engine.run_symbol(sym, sigma_k=sigma_k,
                                     contrarian_at_extreme=contrarian))
    out.sort(key=lambda t: t.entry_ts)
    return out


def line(title, ch="="):
    return f"\n{ch * 78}\n{title}\n{ch * 78}"


def stat_row(label, s):
    if s["n"] == 0:
        return [label, "0", "-", "-", "-", "-", "-", "-"]
    _, final, dd = None, None, None
    return [
        label,
        s["n"],
        f"{s['win_rate']:.1f}%",
        f"[{s['win_rate_lo']:.0f}-{s['win_rate_hi']:.0f}]",
        f"{s['mean_r']:+.4f}",
        f"{s['total_r']:+.1f}",
        f"{s['profit_factor']:.2f}" if s["profit_factor"] != float("inf") else "inf",
        f"{s['t_stat']:+.2f}",
    ]


HEAD = ["", "N", "WinRate", "95% CI", "Mean R", "Total R", "PF", "t"]


def main():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        commit = "unknown"

    report = []
    report.append(line("COT NON-COMMERCIAL WEEKLY DIRECTIONAL BACKTEST"))
    report.append(f"Run             : {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC")
    report.append(f"Commit          : {commit}")
    report.append(f"Universe        : {', '.join(UNIVERSE)}  ({len(UNIVERSE)} instruments)")
    report.append(f"COT source      : CFTC Legacy, Futures-only, Non-Commercial (via TradingView)")
    report.append(f"Price source    : local 4H bars (repo ./data)")
    report.append(f"Account         : {M.START_EQUITY:,.0f} USD, {M.RISK_PER_TRADE:.0%} risk/trade")
    report.append("Entry           : limit at previous Friday's close (gap-fill), placed at the")
    report.append("                  first weekly open AFTER the Friday COT release")
    report.append("Stop / Exit     : 1% adverse move / open of the following week")
    report.append("Costs           : 1 tick slippage on entry and on exit")

    # ---------------------------------------------------------------- sweep
    report.append(line("1. SIGNIFICANCE THRESHOLD SWEEP (all results shown)"))
    report.append("Signal fires when |weekly net change| > k x stdev(net change, trailing 52w).")
    report.append("")
    rows = []
    sweep = {}
    for k in SIGMA_GRID:
        tr = collect(k)
        sweep[k] = tr
        s = M.summarize(tr)
        _, final, dd = M.equity_curve(tr)
        r = stat_row(f"k = {k}", s)
        r.append(f"{final:,.0f}")
        r.append(f"{dd:.1f}%")
        rows.append(r)
    report.append(M.fmt_table(rows, HEAD + ["End Equity", "MaxDD"]))
    report.append("")
    report.append("t = mean R / standard error. |t| < 2 means the edge is not")
    report.append("distinguishable from zero at conventional significance.")

    # pick best by total R purely to *examine* it, not to endorse it
    best_k = max(SIGMA_GRID, key=lambda k: M.summarize(sweep[k])["mean_r"]
                 if M.summarize(sweep[k])["n"] > 0 else -9)
    base = sweep[best_k]

    # ------------------------------------------------- in-sample vs out-of-sample
    report.append(line("2. IS THE BEST THRESHOLD REAL? (in-sample vs out-of-sample)"))
    report.append(f"Best k by mean R over the whole history: k = {best_k}")
    report.append(f"IS  = entries before {OOS_START_YEAR}   OOS = {OOS_START_YEAR} onwards")
    report.append("")
    rows = []
    for k in SIGMA_GRID:
        tr = sweep[k]
        is_t = [t for t in tr if t.year < OOS_START_YEAR]
        oos_t = [t for t in tr if t.year >= OOS_START_YEAR]
        si, so = M.summarize(is_t), M.summarize(oos_t)
        rows.append([
            f"k = {k}",
            si["n"], f"{si['win_rate']:.1f}%" if si["n"] else "-",
            f"{si['mean_r']:+.4f}" if si["n"] else "-",
            so["n"], f"{so['win_rate']:.1f}%" if so["n"] else "-",
            f"{so['mean_r']:+.4f}" if so["n"] else "-",
        ])
    report.append(M.fmt_table(
        rows, ["", "IS N", "IS Win", "IS MeanR", "OOS N", "OOS Win", "OOS MeanR"]))

    # ------------------------------------------------------------ detail at best_k
    s = M.summarize(base)
    _, final, dd = M.equity_curve(base)
    report.append(line(f"3. DETAIL AT k = {best_k}"))
    report.append(f"Trades            : {s['n']}")
    report.append(f"Win rate          : {s['win_rate']:.2f}%  (95% CI {s['win_rate_lo']:.1f}-{s['win_rate_hi']:.1f}%)")
    report.append(f"Mean R            : {s['mean_r']:+.4f}   (SE {s['se_r']:.4f}, t = {s['t_stat']:+.2f})")
    report.append(f"Median R          : {s['median_r']:+.4f}")
    report.append(f"Stdev R           : {s['stdev_r']:.3f}")
    report.append(f"Avg win / avg loss: {s['avg_win_r']:+.3f}R / {s['avg_loss_r']:+.3f}R")
    report.append(f"Profit factor     : {s['profit_factor']:.3f}")
    report.append(f"Expectancy        : {s['expectancy_r']:+.4f}R per trade")
    report.append(f"Total R           : {s['total_r']:+.2f}")
    report.append(f"End equity        : {final:,.0f} USD  (start {M.START_EQUITY:,.0f})")
    report.append(f"Max drawdown      : {dd:.2f}%")
    report.append(f"Stopped out       : {s['stop_rate']:.1f}% of trades")
    report.append(f"Long / Short      : {s['long_pct']:.1f}% / {100 - s['long_pct']:.1f}%")
    report.append(f"At COT extreme    : {s['extreme_pct']:.1f}% of trades (contrarian)")
    report.append(f"Filled at open    : {s['fill_at_open_pct']:.1f}% (gap already through the limit)")

    # -------------------------------------------------------------- breakdowns
    def block(title, groups, order=None):
        report.append(line(title, "-"))
        rows = []
        keys = order if order else sorted(groups.keys(), key=str)
        for kk in keys:
            if kk not in groups:
                continue
            st = M.summarize(groups[kk])
            rows.append(stat_row(f"{kk}{M.small_sample_flag(st['n'])}", st))
        report.append(M.fmt_table(rows, HEAD))

    block("4. BY YEAR (walk-forward view)", M.by_key(base, lambda t: t.year))
    block("5. BY INSTRUMENT", M.by_key(base, lambda t: t.symbol))
    block("6. BY ASSET CLASS", M.by_key(base, lambda t: t.asset_class))
    block("7. BY DIRECTION",
          M.by_key(base, lambda t: "LONG" if t.direction == 1 else "SHORT"))
    block("8. FOLLOW vs CONTRARIAN (extreme rule)",
          M.by_key(base, lambda t: "AT EXTREME (faded)" if t.at_extreme else "NORMAL (followed)"))
    block("9. BY FILL TYPE",
          M.by_key(base, lambda t: "filled at open" if t.filled_at_open else "gap filled intraweek"))

    # ------------------------------------------------ sensitivity of extreme rule
    report.append(line("10. DOES THE 'FADE AT EXTREMES' RULE HELP?"))
    report.append("Same signals, extreme rule switched off (always follow the net change).")
    report.append("")
    rows = []
    for k in SIGMA_GRID:
        with_c = M.summarize(sweep[k])
        without = M.summarize(collect(k, contrarian=False))
        rows.append([
            f"k = {k}",
            with_c["n"], f"{with_c['win_rate']:.1f}%", f"{with_c['mean_r']:+.4f}",
            without["n"], f"{without['win_rate']:.1f}%", f"{without['mean_r']:+.4f}",
        ])
    report.append(M.fmt_table(
        rows, ["", "N", "Win (fade)", "MeanR (fade)", "N", "Win (no fade)", "MeanR (no fade)"]))

    # ------------------------------------------------------------------ export
    csv_path = os.path.join(OUT_DIR, f"trades_k{best_k}.csv")
    with open(csv_path, "w", newline="") as fh:
        if base:
            w = csv.DictWriter(fh, fieldnames=list(asdict(base[0]).keys()))
            w.writeheader()
            for t in base:
                w.writerow(asdict(t))

    meta = {
        "run_utc": dt.datetime.utcnow().isoformat(),
        "commit": commit,
        "universe": UNIVERSE,
        "sigma_grid": SIGMA_GRID,
        "best_k_by_mean_r": best_k,
        "oos_start_year": OOS_START_YEAR,
        "cot_lookback_weeks": 156,
        "significance_lookback_weeks": 52,
        "extreme_hi": 80, "extreme_lo": 20,
        "stop_pct": 0.01, "slippage_ticks": 1,
        "start_equity": M.START_EQUITY, "risk_per_trade": M.RISK_PER_TRADE,
        "n_trades_at_best_k": len(base),
    }
    with open(os.path.join(OUT_DIR, "run_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)

    report.append(line("FILES"))
    report.append(f"Trades CSV : {csv_path}")
    report.append(f"Run meta   : {os.path.join(OUT_DIR, 'run_meta.json')}")

    text = "\n".join(str(x) for x in report)
    with open(os.path.join(OUT_DIR, "report.txt"), "w") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
