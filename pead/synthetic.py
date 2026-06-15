"""Synthetic data generator for offline verification.

Builds OHLC tapes with planted gap events and a controllable
post-event drift. Two profiles supported:

  - earnings: long, persistent drift (60 days), positive-biased
  - news:     shorter, noisier drift (20 days), ~30% mean-revert events,
              higher event-day volume so the vol-multiplier filter triggers
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
    event_drift_mean: float = 0.07,
    event_drift_noise: float = 0.06,
    event_drift_days: int = 60,
    event_negative_frac: float = 0.0,
    event_vol_mult_range: tuple[float, float] = (2.0, 4.0),
) -> pd.DataFrame:
    """Synthetic OHLC tape with planted gap events.

    `event_drift_mean`     — mean cumulative drift over `event_drift_days`
    `event_drift_noise`    — std-dev of planted drift
    `event_drift_days`     — over how many days the drift unfolds
    `event_negative_frac`  — share of events with negative planted drift (mean-revert)
    `event_vol_mult_range` — multiplier on event-day volume
    """
    rng = np.random.default_rng(seed)
    mu_daily = mu_annual / 252.0
    sigma_daily = sigma_annual / np.sqrt(252)

    log_ret = rng.normal(mu_daily, sigma_daily, n_days)

    buffer = max(60, event_drift_days + 20)
    event_days = rng.choice(np.arange(60, n_days - buffer), size=n_events, replace=False)
    event_days.sort()
    event_gaps = rng.uniform(*event_gap_range, size=n_events)

    for day, gap in zip(event_days, event_gaps):
        log_ret[day] += np.log1p(gap)
        is_negative = rng.random() < event_negative_frac
        if is_negative:
            drift_total = rng.normal(-event_drift_mean * 0.6, event_drift_noise)
        else:
            drift_total = rng.normal(event_drift_mean, event_drift_noise)
        per_day = np.log1p(drift_total) / event_drift_days if (1.0 + drift_total) > 0 else 0.0
        log_ret[day + 1 : day + 1 + event_drift_days] += per_day

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
        volume[day] = int(volume[day] * rng.uniform(*event_vol_mult_range))

    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": prices, "Volume": volume},
        index=dates,
    )
    df.attrs["planted_event_days"] = event_days
    df.attrs["planted_gaps"] = event_gaps
    return df


PROFILE_EARNINGS = dict(
    n_events=15,
    event_gap_range=(0.05, 0.20),
    event_drift_mean=0.07,
    event_drift_noise=0.06,
    event_drift_days=60,
    event_negative_frac=0.0,
    event_vol_mult_range=(2.0, 4.0),
)

PROFILE_NEWS = dict(
    n_events=12,
    event_gap_range=(0.08, 0.30),
    event_drift_mean=0.04,
    event_drift_noise=0.08,
    event_drift_days=20,
    event_negative_frac=0.30,
    event_vol_mult_range=(3.5, 6.0),
)


def make_universe(
    n: int = 100,
    profile: str = "earnings",
    **overrides,
) -> dict[str, pd.DataFrame]:
    """Build N synthetic tickers with the chosen edge profile."""
    base = PROFILE_EARNINGS if profile == "earnings" else PROFILE_NEWS
    params = {**base, **overrides}
    out = {}
    for i in range(n):
        ticker = f"SYN{i:03d}"
        out[ticker] = make_stock(ticker, seed=i, **params)
    return out
