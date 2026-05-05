"""Cost model — spreads, slippage, commissions, swaps.

All values per the agreed defaults. Everything is expressed in "price units"
(the same unit as open/high/low/close).

pip_size / point_size: for a given instrument, what is 1 pip / 1 point?
- Forex non-JPY: 0.0001
- Forex JPY:     0.01
- Gold (GC):     0.10  (1 point; GC 'point' = $1)
- Silver (SI):   0.01  (3 cents in display)
- Indices:       0.25 for ES/NQ, 1 for YM/DAX/RTY/NKD (using tick as unit)
- Other futures: use tick from manifest
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostConfig:
    spread_price: float       # total spread in price units
    slippage_price: float     # per-trade total (entry + exit combined, in price units)
    commission_pct: float     # commission as fraction of notional (0.0001 = 1 bp)
    swap_per_night: float     # swap in price units per night held (negative = cost)


def pip_size(name: str, jpy: bool, asset_type: str, tick: float | None) -> float:
    if asset_type == "forex":
        return 0.01 if jpy else 0.0001
    # futures: use tick or reasonable default
    return tick or 0.01


def cost_for(name: str, jpy: bool, asset_type: str, category: str, tick: float | None) -> CostConfig:
    pip = pip_size(name, jpy, asset_type, tick)

    # Forex
    if asset_type == "forex":
        majors = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"}
        if name in majors:
            spread = 0.8 * pip
            slip = 1.0 * pip
            swap = -0.3 * pip
        else:
            spread = 1.8 * pip
            slip = 1.6 * pip
            swap = -0.5 * pip
        comm = 0.00007  # $7 per $100k = 7bp
        return CostConfig(spread, slip, comm, swap)

    # Metals
    if name == "GC":
        return CostConfig(spread_price=0.25, slippage_price=0.20, commission_pct=0.00004, swap_per_night=0.0)
    if name == "SI":
        return CostConfig(spread_price=0.03, slippage_price=0.015, commission_pct=0.00004, swap_per_night=0.0)
    if name in ("HG", "PA", "PL"):
        return CostConfig(spread_price=(tick or 0.0005) * 3, slippage_price=(tick or 0.0005) * 2,
                          commission_pct=0.00004, swap_per_night=0.0)

    # Indices futures
    if category == "index":
        t = tick or 0.25
        return CostConfig(spread_price=t * 2, slippage_price=t * 1, commission_pct=0.00004, swap_per_night=0.0)

    # Energies / other commodities
    if category == "commodity":
        t = tick or 0.01
        return CostConfig(spread_price=t * 2, slippage_price=t * 1, commission_pct=0.00004, swap_per_night=0.0)

    # Default fallback
    t = tick or 0.01
    return CostConfig(spread_price=t * 2, slippage_price=t * 2, commission_pct=0.00005, swap_per_night=0.0)
