# COT Non-Commercial Weekly Directional Backtest

Tests whether weekly changes in CFTC Commitment-of-Traders **non-commercial**
positioning predict the next week's direction.

## Strategy (exactly as specified, nothing fitted to performance)

| Element | Rule |
|---|---|
| Signal source | CFTC Legacy report, Futures-only, Non-Commercial Long/Short |
| Net position | `NonComm Long - NonComm Short` |
| Net change | `net[w] - net[w-1]` |
| Significance | `abs(net_change) > k * stdev(net_change, trailing 52w)` |
| COT Index | Williams %-rank of net over trailing 156w |
| Extreme | COT Index > 80 or < 20 |
| Direction | not extreme -> follow (`sign(net_change)`); at extreme -> **opposite** |
| Entry | LIMIT at the gap-fill level = previous Friday's close |
| Entry timing | first weekly session open **after** the Friday COT release |
| Stop | 1% adverse price move from entry |
| Exit | open of the following week (next COT cycle), or the stop |
| Sizing | 1% of current equity risked per trade, 100,000 USD start |
| Costs | 1 tick slippage on entry and on exit |

Because the stop sits 1% away and 1% of equity is risked, notional equals
equity and a trade's P&L in equity terms is just its direction-adjusted
price return.

## The point-in-time rule

This is the part that decides whether the whole test is meaningful.

A COT bar stamped **Monday 00:00 UTC of week W** describes positions as of
**Tuesday of week W** and is published only on **Friday of week W, 15:30 ET**.
Trading it during week W would use information that did not exist yet — a
5-day look-ahead that would flatter results badly.

The engine therefore requires the entry week to *open* strictly after the
release instant (`report_week + 5 days`). In practice the signal from week W
is traded at the Sunday-evening open of week W+1, which is exactly the
"Friday report -> next market open" rule.

The gap-fill limit price is the close of the last session before the entry
week — also fully known before the order is placed.

## Look-ahead tests

`test_engine.py` includes two mutation tests that are the real proof:

* `test_future_cot_does_not_change_past_decisions` — replace every COT value
  after a cut-off with random numbers; every earlier trade must be bit-identical.
* `test_future_prices_do_not_change_past_decisions` — replace every price bar
  after a trade's exit with garbage; that trade's entry, exit and return must
  be unchanged.

Plus: week-boundary integrity (weekend gap detection survives DST shifts),
duplicate/unsorted timestamps, release-gate ordering, stop distance, and
limit-fill mechanics (marketable vs. resting).

Run: `python3 -m unittest discover -s . -p 'test_*.py'`

## Conservative choices

* Within the 4H bar where the limit fills, we cannot know whether the limit or
  the stop printed first, so the stop is assumed to hit. This biases results
  **down**, never up.
* A limit already through the market at the open fills at the open (the better
  price), which is how a real limit order behaves.
* Slippage is charged against the position on both entry and exit.

## Universe

Instruments need *both* a CFTC COT series and local 4H price history in
`../data`. The set was fixed by data availability and liquidity **before any
result was inspected** — nothing was dropped for performing badly.

Gold and Coffee are absent because the repo's price dataset has no `GC`/`KC`
files; DAX and NKD are absent because they have no CFTC report.

## Files

* `engine.py` — data loading, signal construction, trade simulation
* `metrics.py` — statistics (Wilson intervals, R-multiples, equity curve)
* `run_backtest.py` — threshold sweep, breakdowns, report
* `test_engine.py` — correctness and look-ahead tests
* `data/cot/` — cached COT series (`first_t` + weekly closes)
* `results/` — `report.txt`, `trades_k*.csv`, `run_meta.json`

## Reproducing

```bash
cd cot_backtest
python3 -m unittest discover -s . -p 'test_*.py'
python3 run_backtest.py
```

`results/run_meta.json` records the commit, universe, parameter grid and all
fixed settings for each run.
