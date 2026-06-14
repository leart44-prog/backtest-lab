# PEAD — Post-Earnings-Announcement-Drift backtest

A reproducible backtest of the **Post-Earnings-Announcement-Drift** anomaly on
S&P 500 single stocks, 2023–2025. PEAD is the tendency of a stock to keep
drifting in the direction of its earnings *surprise* (actual vs. consensus EPS)
for weeks after the report.

> **Why this lives in a new `pead/` folder:** the rest of `backtest-lab` is a
> browser/JS engine for **FX & futures**. PEAD is a single-stock equity anomaly
> that needs per-company earnings dates + EPS surprises — data that does not
> exist anywhere in this repo or in `macro-engine`. So this is a self-contained
> Python study rather than a strategy for the existing JS engine.

## TL;DR results

| Finding | Value |
|---|---|
| Universe | 229 S&P 500 names, 2,700 earnings events (2023-01 → 2025-11) |
| **Drift is real**: Q5−Q1 market-adjusted spread @ 60 trading days | **+2.19%** |
| Stable across years (Q5−Q1 @ 60d): 2023 / 2024 / 2025 | +1.79% / +2.26% / +2.28% |
| Where the drift lives | **Almost entirely the short side** — Q1 (negative surprises) ≈ **−2.0%** @60d; Q5 (positive) ≈ flat (+0.15%) |
| Tradeable market-neutral L/S, net 5bp/side, 60d hold | Sharpe **−0.08**, ann. **−1.2%** |
| Tradeable L/S, 20d hold | Sharpe **−0.56** |
| SPY buy & hold over same window (reference) | Sharpe 1.31, +84% |

**Interpretation.** The cross-sectional drift predicted by PEAD is clearly
present and stable year-to-year — but it is **asymmetric** (negative-surprise
stocks keep falling; positive-surprise stocks no longer drift up) and it is
**not profitable as a naive long/short net of costs** in this 2023–2025 sample.
This matches the modern literature: the long leg of PEAD has been largely
arbitraged away since ~2000s, the residual edge sits on the hard-to-harvest
short side, and a narrow, strong bull market (2023–24) is hostile to
market-neutral books. PEAD "works" as a *return predictor*, not as an easy trade.

## Charts (`results/`)

- `fig_drift_curves.png` — cumulative SPY-hedged return by surprise quintile over
  0–60 trading days post-entry. The clean PEAD signature: Q1/Q2 fan downward, Q5 flat.
- `fig_spread_termstructure.png` — Q5−Q1 spread vs holding horizon (edge appears at 40–60d).
- `fig_equity_marketneutral.png` — tradeable market-neutral L/S equity (worked in
  2023, round-tripped to net-negative by 2025).

## Method (point-in-time safe)

| Step | Choice |
|---|---|
| Signal | analyst surprise `Surprise% = ReportedEPS − EstimateEPS` (yfinance) |
| Entry | **close of the first full trading day _after_ the report is public** (AMC → next session, BMO → announcement-day session). Deliberately skips the announcement jump and trades only the *drift*. |
| Return | adjusted-close return entry → entry+k trading days, k ∈ {1,5,10,20,40,60} |
| Market adj. | minus SPY return over identical dates |
| Event study | mean SPY-hedged drift path per **full-sample** surprise quintile (descriptive; uses full-sample breakpoints, so not tradeable) |
| Tradeable | long top / short bottom surprise names with breakpoints from a **trailing 120-day** surprise distribution (no look-ahead), equal-weight, **SPY-hedged** (market neutral), net of 5 bp/side costs |

Look-ahead controls: entry strictly after public release; AMC/BMO classified from
the announcement timestamp; tradeable breakpoints use only past surprises.

## Reproduce

```bash
pip install pandas numpy matplotlib scipy
cd pead
python3 pead_backtest.py        # reads data/, writes results/  (no network)
python3 fetch_data.py           # OPTIONAL: rebuild data/ from public sources
```

## Data & provenance (`data/`)

The environment's network policy allows only PyPI + GitHub, so every
conventional market-data API (Yahoo, Nasdaq, SEC, AlphaVantage, FMP, stooq)
returns HTTP 403. Data is therefore assembled from public datasets other authors
committed to GitHub:

- **Earnings surprises** — `Chinar-byte/FINS3666-Group-Project` (`earnings_data/*_earnings.csv`,
  yfinance `get_earnings_dates()` exports, ~230 S&P 500 names, 2021-2025).
- **Daily adjusted prices** — merged from `magiccpp/price_data` (2023-01..2025-05)
  and `do0405/invest-prototype` (`data/us/`, 2024-12..2026-04) for 2023-01..2026-04 coverage.

Committed files: `earnings_events.csv` (4,177 events), `prices_panel.csv.gz`
(188,548 ticker-days incl. SPY).

## Data quality & limitations

- **Third-party, non-audited data.** EPS estimates/actuals are yfinance/consensus
  snapshots, not point-in-time vendor data; estimates may be post-revision and EPS
  is not split for one-offs. Treat magnitudes as indicative.
- **Survivorship bias.** Universe ≈ current/recent S&P 500 members → mild upward bias.
- **Short period (≈3 yrs).** Covers a specific bull-market regime; not a full-cycle test.
- **`Surprise%` not true SUE.** Standardized Unexpected Earnings (surprise ÷ its own
  historical vol) is the cleaner signal; not enough committed history here to build it robustly.
- **Costs/borrow.** 5 bp/side modeled; short-borrow fees, slippage and shorting
  feasibility are not — they would further hurt the (short-dependent) edge.
