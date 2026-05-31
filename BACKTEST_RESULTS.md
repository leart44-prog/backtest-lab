# Backtest — Pete's "Pullback in Trend" on Dukascopy H1

Reproducible headless run of the dashboard engine (`js/*.js`) over freshly
fetched **Dukascopy H1** data.

## How to reproduce

```bash
cd tools
npm install
node fetch_dukascopy.mjs --tf h1 --from 2013-01-01     # all 28 FX pairs, H1
node run_backtest.mjs                                   # Pete's pullback strategy, all pairs
node run_backtest.mjs --petes-exit                      # quick 1:1 variant (single TP 1.0R/100%, no trail)
```

`run_backtest.mjs` loads the exact same modules the browser Web Worker uses
(`data-loader`, `backtest-engine`, `analytics`, `strategy-pullback`) and runs
them with the dashboard's default settings, so the numbers match the UI.

## Data

- **Source:** Dukascopy (tick-aggregated), bid prices, H1.
- **Range:** 2013-01-01 → 2026-05-30 — 117,552 H1 bars per pair, 28 FX pairs
  (~3.29M bars total).
- `data/pairs.json` was rebuilt by the fetcher and now lists the 28 H1 FX pairs
  (`timeframe: "h1", source: "dukascopy"`).

## Configuration (dashboard defaults)

| | |
| --- | --- |
| Strategy | Pullback in Trend — Stoch(14,3,3) 20/80, EMA 50/200, require HH/LL, SL = swing(10) ± 0.5 ATR |
| Trade mgmt | TP 1R/2R/3R @ 50/30/20%, BE after TP1, trail after TP2 (1.0 ATR), max 80 bars |
| Costs | spread 2.0 pips + slippage 0.5 pips |
| Sizing | 10,000 start, 1% risk/trade |

## Result — all 28 pairs, default scale-out exit

| Metric | Value |
| --- | --- |
| Total trades | 30,187 (15,374 long / 14,813 short) |
| Win rate | 44.1% (13,309 W / 16,878 L) |
| Total R | **−3,082.3 R** |
| Expectancy | −0.102 R/trade (avg win +1.00R, avg loss −0.97R) |
| Profit factor | 0.81 |
| Sharpe / Sortino | −1.55 / −2.20 |
| Max drawdown | 100% (3,085 R) |
| Profitable years | 0 / 14 |

Exit mix: SL 16,228 (−16,228 R) · TRAIL_SL 4,693 (+6,898 R) · TP3 1,562
(+2,655 R) · BE_SL 5,180 (+2,331 R) · TIMEOUT 2,524 (+1,262 R).

Best/worst pairs by R: GBPJPY (−2.7 R) … GBPNZD (−37 R) on the strong end;
NZDCHF (−186 R), EURCHF (−179 R) on the weak end. Every pair is net-negative.

## Result — Pete's quick 1:1 variant (`--petes-exit`)

Single TP at 1.0R / 100%, no break-even step, no trailing:

| Metric | Value |
| --- | --- |
| Total trades | 30,969 |
| Win rate | 44.0% |
| Total R | **−3,694.7 R** |
| Expectancy | −0.119 R/trade (avg win +0.97R, avg loss −0.98R) |
| Profit factor | 0.78 |

Slightly worse than the scale-out exit on this un-tuned full-universe run — the
1:1 exit gives up the fat right tail that TRAIL_SL/TP3 contribute above.

## Interpretation

This confirms the note in the README: **with un-tuned, one-size-fits-all
parameters across all 28 pairs over 13 years the edge is negative.** The
strategy is designed to be tuned per pair on its operating timeframe — the value
of this run is the clean H1 dataset + a reproducible harness to optimise against,
not the headline P&L. Avg win ≈ avg loss with a sub-50% hit rate is exactly the
profile you'd expect from an untuned mean-reversion-in-trend system once spread
is charged on every entry.

Sensible next steps: per-pair parameter sweeps (stoch thresholds, EMA lengths,
SL buffer), restricting to the pairs/sessions where the structure filter adds
edge, and comparing the `--petes-exit` quick-1:1 variant against the scale-out.

---

# Reproducing Pete's per-pair report (`tools/run_petes.mjs`)

Pete's `Backtest_Master_Report_All_12_Pairs` reports, for **27 Apr – 30 May
2026** (one month, 12 pairs): **58 trades, 67.2% win rate, +1,394 pips, +94.8k
(≈ +95%)**. Each pair uses a tuned Stochastic plus a **fixed-pip stop (6–10 p)
and a fixed-pip target (20–50 p)** → RR 1:2.5 … 1:8.3 (avg 1:4.9).

To test this we added an opt-in `fixed_pips` mode + entry-window gating to the
engine and replayed his exact per-pair table on our independent Dukascopy H1
data — same window first, then the full 13-year history out-of-sample.

## Same window (27 Apr – 30 May 2026), Pete's exact parameters

| | Pete's report | This engine (spread 0) | This engine (0.8p) |
| --- | --- | --- | --- |
| Trades | 58 | **56** | 56 |
| Win rate | **67.2%** | **14.3%** | 12.5% |
| Total pips | +1,394 | **−127** | −169 |
| Expectancy | huge + | −0.33 R | −0.42 R |

The **trade count matches (56 vs 58)** — entries and data line up well — but the
**win rate is inverted**. Our 14% is essentially the random-walk baseline: for an
average RR of 1:4.9 the geometric break-even hit rate is ~1/(1+4.9) ≈ **17%**. In
other words the Stoch entries add ~no directional edge; outcomes are dominated by
the geometry of a tiny stop vs a wide target.

## Full out-of-sample, 2013 → 2026 (same 12 pairs, same params)

| | spread 0.8p | spread 0 |
| --- | --- | --- |
| Trades | 7,706 | 7,687 |
| Win rate | 16.5% | 18.4% |
| Total pips | −8,813 | −2,833 |
| Expectancy | −0.147 R | −0.044 R |
| Profit factor | 0.82 | 0.95 |
| Equity (1% risk) | → 0 | → ~0 |

Every pair is net-negative out-of-sample; even with **zero** trading costs the
system loses. Win rate holds at ~16–18% — exactly the no-edge baseline — across
13 years and ~7,700 trades.

## Diagnosis

The near-perfect trade-count match with an inverted win rate points to a
**fill/sequencing artifact in Pete's backtest, not a real edge**:

- A 6–10 pip stop is **smaller than a single H1 bar's range** (AUDCAD H1 ATR ≈
  15–25 pips). Whether SL or TP is hit first is decided *inside* the bar, which
  H1 OHLC cannot resolve.
- This engine resolves the ambiguity **conservatively** (checks the bar's low/high
  against the stop *before* the target), so a bar that touches both counts as a
  loss. That yields the ~14–18% baseline.
- Pete's 67% implies the **opposite** convention — the target is credited before
  the stop (or only the close is checked), flipping most intrabar losers into
  winners. With a stop this tight that single assumption is the entire result.
- One-month, in-sample-tuned parameters then make the headline number look
  spectacular; it does not survive out-of-sample.

**Bottom line:** the strategy as parameterised has no demonstrable out-of-sample
edge on clean tick-aggregated H1 data. Before trading it, Pete's backtester needs
either (a) tick/M1 data so 6–10 pip stops can be filled honestly, or (b) a
documented, conservative intrabar fill rule — and the parameters must be
validated out-of-sample, not on the month they were fitted to.

Reproduce:

```bash
cd tools && npm install
node run_petes.mjs --from 2026-04-27 --to 2026-05-30   # his window
node run_petes.mjs                                      # full out-of-sample
node run_petes.mjs --spread 0                           # zero-cost best case
```
