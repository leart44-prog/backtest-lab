# PEAD backtester

Detects earnings-gap events on an equity universe and simulates the
"long-after-the-breakout-candle" trade with a dynamic trailing stop.

## Trade rules

- **Trigger**: Day-1 open is `>= gap_pct` (default 5 %) above Day-0 close
- **Entry**: Day-1 close
- **Initial stop**: Day-1 low
- **Trail**: 10-day SMA after day 5, 20-day SMA after day 30
- **Forced exit**: stop hit | close < 50-EMA (checked every 5 days) | day 60

## Run

Verify offline with planted-edge synthetic data (no network needed):

```sh
cd /path/to/backtest-lab
uv run --project pead python -m pead.run --synthetic
```

Null-hypothesis sanity check (planted drift = 0):

```sh
uv run --project pead python -m pead.run --synthetic --null
```

Real data on S&P 100:

```sh
uv run --project pead python -m pead.run --years 10 --gap-pct 0.05 --out trades.csv
```

Custom universe:

```sh
uv run --project pead python -m pead.run --tickers MU,NVDA,AVGO,AMD --years 5
```

`yfinance` data is cached under `data/equities/<TICKER>.parquet`. Re-runs
reuse the cache. Set `FORCE_REFRESH=1` to bypass.

## What it reports

- Headline cohort stats (win rate, profit factor, expectancy, Sharpe)
- Stratified table by gap size (5-10 %, 10-15 %, 15-20 %, >=20 %)
- Sequential equity curve at 5 % position size per trade
- Optional CSV of every trade
