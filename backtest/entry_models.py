"""Entry order-type models for S/D zone signals.

All models consume the SAME first-touch signals (sd_zones.find_zone_touches),
so differences in outcome are attributable to order type alone.

Models (long side described; shorts mirrored):

  LIMIT          Resting limit at the proximal edge. Fills on the touch bar.
                 If that bar also trades through the SL level -> -1R (honest
                 same-bar stopout).

  STOP_HIGH      After the touch bar T closes, buy-stop at high(T) + buf*ATR,
                 valid for `validity` bars. Cancelled if price reaches the SL
                 level before triggering. Trigger bar that also touches SL ->
                 conservative -1R.

  STOP_RECLAIM   Buy-stop at proximal + buf*ATR (price must have dipped into
                 the zone, then come back up through it). If the touch bar
                 already closes above the trigger, enter market-on-close of T.
                 Otherwise valid `validity` bars, same cancel/conservative
                 rules as STOP_HIGH.

  CLOSE_CONFIRM  Enter market-on-close of the first bar (T..T+validity) that
                 closes back above the proximal edge. Cancelled if the SL
                 level trades before a confirming close appears.

Conservatism notes:
  - Mid-bar fills (LIMIT, stop triggers) ignore same-bar favorable follow-
    through but take the same-bar SL as -1R: pessimistic for those models.
  - CLOSE_CONFIRM enters at bar close, so it has no same-bar ambiguity.
  - Friction (spread+slippage) is identical across models. Real stop-market
    fills tend to get slightly worse slippage than resting limits; the
    comparison is therefore mildly biased IN FAVOR of the stop models.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ENTRY_MODELS = ("LIMIT", "STOP_HIGH", "STOP_RECLAIM", "CLOSE_CONFIRM")


def fill_signal(
    sig: dict,
    df: pd.DataFrame,
    model: str,
    friction: float,
    buf_atr: float = 0.10,
    validity: int = 6,
) -> dict | None:
    """Resolve one signal under one entry model.

    Returns None if no fill (cancelled/expired), else dict with:
      entry_i, entry, stop, same_bar_stopout (bool)
    """
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)

    T = sig["touch_i"]
    side = sig["side"]
    prox = sig["proximal"]
    sl = sig["sl_level"]
    atr = sig["atr"]
    sgn = 1.0 if side == "long" else -1.0

    def adverse_hit(i: int) -> bool:
        return (l[i] <= sl) if side == "long" else (h[i] >= sl)

    if model == "LIMIT":
        entry = prox + sgn * friction
        if sgn * (entry - sl) <= 0:
            return None
        return {"entry_i": T, "entry": entry, "stop": sl,
                "same_bar_stopout": adverse_hit(T)}

    if model in ("STOP_HIGH", "STOP_RECLAIM"):
        if model == "STOP_HIGH":
            trigger = (h[T] + buf_atr * atr) if side == "long" else (l[T] - buf_atr * atr)
            start = T + 1
        else:  # STOP_RECLAIM
            trigger = prox + sgn * buf_atr * atr
            # touch bar already closed beyond trigger -> market-on-close entry
            if sgn * (c[T] - trigger) >= 0:
                entry = c[T] + sgn * friction
                if sgn * (entry - sl) <= 0:
                    return None
                return {"entry_i": T, "entry": entry, "stop": sl,
                        "same_bar_stopout": False}
            start = T + 1

        for B in range(start, min(T + validity, n - 1) + 1):
            triggered = (h[B] >= trigger) if side == "long" else (l[B] <= trigger)
            if triggered:
                entry = trigger + sgn * friction
                if sgn * (entry - sl) <= 0:
                    return None
                # conservative: if the trigger bar also touches SL, -1R
                return {"entry_i": B, "entry": entry, "stop": sl,
                        "same_bar_stopout": adverse_hit(B)}
            if adverse_hit(B):
                return None    # SL region traded before trigger -> cancel
        return None            # expired

    if model == "CLOSE_CONFIRM":
        for B in range(T, min(T + validity, n - 1) + 1):
            # violation has priority: once the SL level trades, the zone is
            # invalid even if the same bar closes back above the edge
            if adverse_hit(B):
                return None
            confirmed = (c[B] > prox) if side == "long" else (c[B] < prox)
            if confirmed:
                entry = c[B] + sgn * friction
                if sgn * (entry - sl) <= 0:
                    return None
                return {"entry_i": B, "entry": entry, "stop": sl,
                        "same_bar_stopout": False}
        return None

    raise ValueError(model)
