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
