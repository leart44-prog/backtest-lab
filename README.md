# backtest-lab

A standalone, browser-based backtesting dashboard for Forex & Futures. All
computation runs client-side in a Web Worker — open `index.html` (or serve the
folder) and go. No build step for the dashboard itself.

## Strategies

The **Strategy** dropdown offers three engines:

| Strategy | Description |
| --- | --- |
| **Playbook v5 — Pattern Zones** | Supply/Demand pattern zones (DBR/RBR/DBD/RBD) with EMA 50/200 trend, freshness & level-on-level. |
| **Pullback in Trend — Stoch + HH/LL** | "Pullbacks within a trend" — see below. |
| **Pine Script (Custom)** | Write a (subset of) Pine and have it transpiled to JS at runtime. |

### Pullback in Trend (Stoch + HH/LL)

A faithful port of the *"Pullbacks within a trend"* logic: trade pullbacks in
the direction of the prevailing trend, timed by a Stochastic reversal and
confirmed by market structure.

A position triggers when **all** of the following align:

1. **Trend** — EMA fast vs slow (default 50/200) defines long/short bias
   (optional minimum EMA gap in ATR).
2. **Stochastic reversal out of the pullback** — for longs, %K dips into the
   oversold zone and turns back up (crosses the level, or crosses %D); mirror
   for shorts (overbought).
3. **Structure confirmation** — the trend structure shows a **Higher High**
   (long) / **Lower Low** (short), detected from confirmed fractal swing pivots
   (no look-ahead). Switchable to a `breakout` mode (new high/low on the signal
   bar) or disabled entirely.

Stop loss sits behind the recent swing low/high plus an ATR buffer; the engine
derives R-multiple take-profits, break-even and trailing from there. For Pete's
"quick 20-pip, RR 1:1" exit, set a single TP at `1.0 R / 100%` and disable
trailing in the **Trade Management** panel.

Source: [`js/strategy-pullback.js`](js/strategy-pullback.js). All parameters are
exposed in the sidebar panel.

> Note on expectations: like any optimised pullback system, results are highly
> timeframe- and parameter-dependent. On un-tuned multi-year 4H data the edge is
> thin/negative; it is designed to be tuned per pair on the operating timeframe
> (H1).

## Data

Bars are stored as gzipped JSON arrays of `[unixSeconds, open, high, low, close]`
in `data/<PAIR>.json.gz`, with a `data/pairs.json` manifest. The loader
(`js/data-loader.js`) fetches and decompresses these in the browser.

### Dukascopy H1 pipeline (recommended)

The most accurate FX data comes from **Dukascopy** (tick-aggregated). Fetch H1
(or any timeframe) bars for all 28 FX pairs with:

```bash
cd tools
npm install
node fetch_dukascopy.mjs                  # all 28 FX pairs, H1, 2013 → today
node fetch_dukascopy.mjs --pairs EURUSD,GBPUSD --tf h1 --from 2024-01-01
```

This writes `data/<PAIR>.json.gz` + rebuilds `data/pairs.json`. See
[`tools/fetch_dukascopy.mjs`](tools/fetch_dukascopy.mjs) for all flags.

**Network requirement:** the downloader reaches `datafeed.dukascopy.com`. In a
locked-down Claude Code web environment that host is blocked by the network
policy (`Host not in allowlist`). Add `datafeed.dukascopy.com` to the
environment's allowlist, or run the fetcher locally, before invoking. See
https://code.claude.com/docs/en/claude-code-on-the-web for network-policy
configuration.

### Building from local CSVs (legacy)

`build_static_data.py` builds the bundles from local 4H TradingView/OANDA CSV
exports (see the path constants at the top of the file).
