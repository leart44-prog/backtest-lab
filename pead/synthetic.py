"""Synthetic data generator for offline verification.

Builds OHLC tapes with planted earnings-gap events and a controllable
post-event drift. Used to validate the backtest detects the planted edge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_stock(
    ticker: str,
    n_days: int = 2500,
    start: str = "2015-01-01",
    seed: int = 0,
    mu_annual: float = 0.10,
    sigma_annual: float = 0.25,
    n_events: int = 15,
    event_gap_range: tuple[float, float] = (0.05, 0.20),
    event_drift_60d: float = 0.07,
    event_drift_noise: float = 0.06,
) -> pd.DataFrame:
    """Generate a synthetic OHLC tape with planted PEAD events.

    `event_drift_60d` is the mean planted 60-day excess return after each
    event (the academic PEAD effect). Set to 0.0 for a null-hypothesis tape.
    """
    rng = np.random.default_rng(seed)
    mu_daily = mu_annual / 252.0
    sigma_daily = sigma_annual / np.sqrt(252)

    log_ret = rng.normal(mu_daily, sigma_daily, n_days)

    event_days = rng.choice(np.arange(60, n_days - 80), size=n_events, replace=False)
    event_days.sort()
    event_gaps = rng.uniform(*event_gap_range, size=n_events)

    for day, gap in zip(event_days, event_gaps):
        log_ret[day] += np.log1p(gap)  # the open gap
        drift_total = rng.normal(event_drift_60d, event_drift_noise)
        per_day = np.log1p(drift_total) / 60.0
        log_ret[day + 1 : day + 61] += per_day

    prices = 100.0 * np.exp(log_ret.cumsum())
    dates = pd.bdate_range(start=start, periods=n_days)

    intraday_range = np.abs(rng.normal(0.0, 0.012, n_days))
    high = prices * (1 + intraday_range)
    low = prices * (1 - intraday_range)
    open_ = np.r_[prices[0], prices[:-1] * np.exp(rng.normal(0, 0.005, n_days - 1))]
    for day, gap in zip(event_days, event_gaps):
        if day > 0:
            open_[day] = prices[day - 1] * (1 + gap * 0.95)
            high[day] = max(high[day], open_[day], prices[day]) * (1 + 0.01)
            low[day] = min(low[day], prices[day - 1] * (1 + gap * 0.5))

    volume = rng.integers(1_000_000, 5_000_000, n_days)
    for day in event_days:
        volume[day] = int(volume[day] * rng.uniform(2.0, 4.0))

    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": prices, "Volume": volume},
        index=dates,
    )
    df.attrs["planted_event_days"] = event_days
    df.attrs["planted_gaps"] = event_gaps
    return df


def make_universe(n: int = 100, drift_60d: float = 0.07, drift_noise: float = 0.06) -> dict[str, pd.DataFrame]:
    """N synthetic tickers with planted PEAD edge."""
    out = {}
    for i in range(n):
        ticker = f"SYN{i:03d}"
        out[ticker] = make_stock(ticker, seed=i, event_drift_60d=drift_60d, event_drift_noise=drift_noise)
    return out
