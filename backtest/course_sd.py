"""Python port of the user's Pine v5 "Supply & Demand — Course Method"
indicator (RBR/DBR/RBD/DBD) + Pine v6 "Valuation Score", with the user's
trade management.

Pine-fidelity notes (mapping to the original script):
  - f_scan(): leg-out on current bar (explosive: body%>0.70 & range>=1.5x
    avgR[1]; decisive-big; gap-inclusive move), base = consecutive indecisive
    candles (body%<=0.50 or range<0.5x avgR), max 6, leg-in decisive/explosive,
    speed-bump filter, departure/base scores. Zones formed on CONFIRMED bars
    only (no repainting).
  - Zone bounds: preferred proximal = base body extreme, wider = base wick
    extreme; distal includes the leg-out extreme (leg-in excluded), exactly
    like the script.
  - Freshness/mitigation: touches tracked on wider+preferred lines from the
    bar AFTER creation; close beyond distal mitigates.
  - Valuation Score: Hybrid mode (z-score of ROC(ratio), window 100, smooth 3,
    x30, clamp +/-150). FX ratios from real 6E/6B/6A/6N/6C/6S/6J futures data
    (exact); indices & metals/commodities use the equal-weight class basket as
    benchmark (documented deviation: ZB/GC data not available).

User trade rules implemented:
  - Limit order at the preferred proximal edge, only while the zone is
    tradeable: fresh OR exactly 1 prior touch with penetration <= 25% of zone
    height.
  - Valuation gate: demand entries only when score <= -t1, supply only when
    score >= +t1 (class-specific t1 presets from the indicator).
  - SL = 25% of zone height beyond the distal. TP = 2.5R. Stop-before-target,
    same-bar violation = -1R (honest fills), costs baked into entry.
  - Stacked zones: overlapping same-direction active zones -> only the distal
    (deeper) one is tradeable.
  - Optional HTF coverage: LTF zone nested inside a same-direction active
    DAILY zone (computed with the same f_scan on resampled daily bars).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import cost_for
from .data import load_manifest, load_bars

FX_FUT = {"EUR": "6E", "GBP": "6B", "AUD": "6A", "NZD": "6N",
          "CAD": "6C", "CHF": "6S", "JPY": "6J"}

UNIVERSE = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCAD", "AUDCHF", "AUDNZD",
    "NZDJPY", "NZDCAD", "NZDCHF", "CADJPY", "CADCHF", "CHFJPY",
    "ES", "NQ", "YM", "RTY", "DAX", "NKD",
    "SI", "HG", "PL", "PA", "CL", "NG",
]


def asset_class(name: str) -> str:
    if name in ("ES", "NQ", "YM", "RTY", "DAX", "NKD"):
        return "indices"
    if name in ("SI", "HG", "PL", "PA"):
        return "metals"
    if name in ("CL", "NG"):
        return "commodities"
    if len(name) == 6:
        return "fx_major" if "USD" in name else "fx_cross"
    return "other"


# ─────────────────────────────────────────────────────────────────────
# Zone detection — faithful f_scan() port, vectorized per bar index
# ─────────────────────────────────────────────────────────────────────
@dataclass
class CZone:
    is_demand: bool
    fcode: int              # 1 RBR, 2 DBR, 3 RBD, 4 DBD
    prox_w: float           # wider proximal (wicks)
    prox_p: float           # preferred proximal (bodies)
    distal: float
    created_i: int
    dep: int                # departure score 0-2
    base_sc: int
    touches: int = 0        # touches counted AFTER creation
    max_penetration: float = 0.0   # deepest touch, fraction of zone height
    mitigated: bool = False
    lol: bool = False       # level-on-level (near/overlapping same-direction zone)


def scan_zones(df: pd.DataFrame, avg_len: int = 10, size_factor: float = 1.5,
               max_base: int = 6, filter_speed_bump: bool = True) -> list[CZone]:
    """Detect all zones over the whole series. Zone formed at bar i uses only
    bars <= i (confirmed-bar semantics)."""
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    rng = h - l
    avg_r = pd.Series(rng).rolling(avg_len).mean().to_numpy()

    zones: list[CZone] = []
    for i in range(max_base + avg_len + 2, n):
        r0 = rng[i]
        b0 = abs(c[i] - o[i])
        bp0 = b0 / r0 if r0 > 0 else 0.0
        a1 = avg_r[i - 1] if np.isfinite(avg_r[i - 1]) else r0
        big0 = r0 >= size_factor * a1
        expl0 = bp0 > 0.70 and big0
        dec0 = bp0 > 0.50 and not (r0 < 0.5 * a1)
        up_move = h[i] - c[i - 1]
        dn_move = c[i - 1] - l[i]
        big_up = up_move >= size_factor * a1
        big_dn = dn_move >= size_factor * a1
        leg_out_bull = c[i] > o[i] and (expl0 or (dec0 and big0) or big_up)
        leg_out_bear = c[i] < o[i] and (expl0 or (dec0 and big0) or big_dn)
        if not (leg_out_bull or leg_out_bear):
            continue

        # count consecutive indecisive base candles ending at i-1
        b_len = 0
        for k in range(1, max_base + 1):
            j = i - k
            if j < 1:
                break
            rk = rng[j]
            bk = abs(c[j] - o[j])
            bpk = bk / rk if rk > 0 else 0.0
            ak = avg_r[j - 1] if np.isfinite(avg_r[j - 1]) else rk
            smallk = rk < 0.5 * ak
            indk = bpk <= 0.50 or smallk
            if indk:
                b_len = k
            else:
                break
        if b_len < 1:
            continue

        li = i - b_len - 1
        if li < 1:
            continue
        rli = rng[li]
        bli = abs(c[li] - o[li])
        bpli = bli / rli if rli > 0 else 0.0
        ali = avg_r[li - 1] if np.isfinite(avg_r[li - 1]) else rli
        bigli = rli >= size_factor * ali
        # decisive = body%>0.50 AND not tiny-range (audit fix: Pine parity)
        decli = bpli > 0.50 and not (rli < 0.5 * ali)
        expl_li = bpli > 0.70 and bigli
        if not (decli or expl_li):
            continue

        leg_in_bull = c[li] > o[li]
        is_dem = leg_out_bull
        base_slice = slice(i - b_len, i)
        b_high = h[base_slice].max()
        b_low = l[base_slice].min()
        b_body_hi = np.maximum(o[base_slice], c[base_slice]).max()
        b_body_lo = np.minimum(o[base_slice], c[base_slice]).min()
        same_dir = leg_in_bull == leg_out_bull

        if is_dem:
            pw, pp, dd = b_high, b_body_hi, min(b_low, l[i])
        else:
            pw, pp, dd = b_low, b_body_lo, max(b_high, h[i])
        fcode = (1 if leg_in_bull else 2) if is_dem else (3 if leg_in_bull else 4)
        dep_big = (dec0 and big0) or (big_up if is_dem else big_dn)
        dep = 2 if expl0 else (1 if dep_big else 0)
        bsc = 2 if 2 <= b_len <= 4 else 1
        speed_bump = filter_speed_bump and b_len == 1 and same_dir and (expl_li or (decli and bigli))
        if dep >= 1 and not speed_bump:
            zones.append(CZone(is_dem, fcode, float(pw), float(pp), float(dd),
                               i, dep, bsc))
    return zones


# ─────────────────────────────────────────────────────────────────────
# Valuation Score — Hybrid mode port
# ─────────────────────────────────────────────────────────────────────
def valuation_score(name: str, df: pd.DataFrame, fut: dict[str, pd.Series],
                    class_baskets: dict[str, pd.Series],
                    z_len: int = 100, z_smooth: int = 3, z_mult: float = 30.0
                    ) -> tuple[pd.Series, float]:
    """Returns (score series aligned to df.index, t1 threshold)."""
    klass = asset_class(name)
    if klass in ("fx_major", "fx_cross"):
        base_ccy, quote_ccy = name[:3], name[3:]
        # as-of alignment (audit fix: FX spot and futures grids share no exact
        # timestamps; exact-match reindex produced an all-NaN dead series)
        bv = pd.Series(1.0, index=df.index) if base_ccy == "USD" else \
            fut[FX_FUT[base_ccy]].reindex(df.index, method="ffill")
        qv = pd.Series(1.0, index=df.index) if quote_ccy == "USD" else \
            fut[FX_FUT[quote_ccy]].reindex(df.index, method="ffill")
        ratio = bv / qv
        t1 = 60.0 if klass == "fx_cross" else 70.0
        roc_len = 10
    else:
        bench = class_baskets[klass].reindex(df.index).ffill()
        ratio = df["close"] / bench
        t1 = 80.0
        roc_len = 15 if klass == "indices" else 10

    roc = ratio / ratio.shift(roc_len) - 1.0
    mu = roc.rolling(z_len).mean()
    sig = roc.rolling(z_len).std(ddof=0)   # Pine ta.stdev = population std
    raw = np.where(sig > 0, (roc - mu) / sig, np.nan)   # NaN, not 0 (audit fix)
    smooth = pd.Series(raw, index=df.index).rolling(z_smooth).mean()
    score = (smooth * z_mult).clip(-150, 150)
    return score, t1


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────
def run_course_sd(
    name: str,
    df: pd.DataFrame,
    score: pd.Series | None,
    t1: float,
    daily_zones: list[CZone] | None,
    daily_index: pd.DatetimeIndex | None,
    use_valuation: bool,
    use_htf: bool,
    fresh_mode: str = "user",      # "fresh_only" | "user" (<=1 touch, <=25% pen) | "any"
    stop_pct: float = 0.25,
    target_r: float = 2.5,
    max_zone_age: int = 500,
    location_gate: bool = False,   # Bernd spec: long only low/very-low, short only high/very-high
    trend_gate: bool = False,      # Bernd spec: daily pivot structure; counter-trend needs clean arrival
    pm_gate: bool = False,         # Bernd spec: >=2R headroom to nearest opposing LTF zone
    arrival_gate: bool = False,    # Bernd spec: clean impulsive approach to the zone
    daily_trend: "np.ndarray | None" = None,
    formations: tuple[int, ...] = (1, 2, 3, 4),
    zone_scanner=None,
) -> list[dict]:
    meta = {m["name"]: m for m in load_manifest()}[name]
    cost = cost_for(name, meta.get("jpy", False), meta["type"], meta["category"],
                    meta.get("tick"))
    friction = cost.spread_price + cost.slippage_price

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    n = len(df)
    score_v = score.to_numpy() if score is not None else None

    all_zones = (zone_scanner or scan_zones)(df)
    zones_by_bar: dict[int, list[CZone]] = {}
    for z in all_zones:
        zones_by_bar.setdefault(z.created_i, []).append(z)

    # daily HTF zone activity intervals for coverage lookup
    #   active from creation until mitigated (close beyond distal on daily)
    # populated whenever daily zones exist — needed by BOTH the coverage gate
    # (use_htf) and the location gate (bugfix: was gated on use_htf only,
    # leaving the location gate with an empty list)
    htf_active: list[tuple[int, int, CZone]] = []
    if daily_zones is not None and daily_index is not None:
        htf_active = [(z.created_i, getattr(z, "mit_i", 10**9), z) for z in daily_zones]

    def htf_covered(zone: CZone, ts: pd.Timestamp) -> bool:
        if not use_htf or daily_index is None:
            return True
        # audit fix: only fully COMPLETED daily bars count. normalize() maps to
        # the current (in-progress) day; -1 steps to the last closed day. A
        # zone becomes active only AFTER its creation day closed (start_i < d_i)
        # and mitigation is only known after the mitigation day closed.
        d_i = daily_index.searchsorted(ts.normalize()) - 1
        for start_i, end_i, hz in htf_active:
            if hz.is_demand != zone.is_demand:
                continue
            if not (start_i < d_i < end_i):
                continue
            if zone.is_demand:
                if zone.prox_p <= hz.prox_p and zone.distal >= hz.distal:
                    return True
            else:
                if zone.prox_p >= hz.prox_p and zone.distal <= hz.distal:
                    return True
        return False

    def daily_pos(ts: pd.Timestamp, price: float):
        """Location band from nearest ACTIVE daily zones (completed days only).
        Returns fraction of the demand-distal..supply-distal span, or None."""
        if daily_index is None or daily_zones is None:
            return None
        d_i = daily_index.searchsorted(ts.normalize()) - 1
        dem_d, sup_d = None, None
        for start_i, end_i, hz in htf_active:
            if not (start_i < d_i < end_i):
                continue
            if hz.is_demand and hz.distal <= price:
                if dem_d is None or hz.distal > dem_d:
                    dem_d = hz.distal
            elif (not hz.is_demand) and hz.distal >= price:
                if sup_d is None or hz.distal < sup_d:
                    sup_d = hz.distal
        if dem_d is None or sup_d is None or sup_d <= dem_d:
            return None
        return (price - dem_d) / (sup_d - dem_d)

    def arrival_clean(zone: CZone, i: int) -> bool:
        """Objective arrival check: price came from >=0.75 zone-heights away
        within <=8 bars, and no opposing zone formed during the approach."""
        height = abs(zone.prox_p - zone.distal)
        lo_k = max(0, i - 12)
        window = c[lo_k:i]
        if len(window) == 0:
            return False
        if zone.is_demand:
            jrel = int(np.argmax(window))
            far_enough = (window[jrel] - zone.prox_p) >= 0.75 * height
        else:
            jrel = int(np.argmin(window))
            far_enough = (zone.prox_p - window[jrel]) >= 0.75 * height
        jabs = lo_k + jrel
        if not far_enough or (i - jabs) > 8:
            return False
        for zz in all_zones:
            if zz.is_demand != zone.is_demand and jabs < zz.created_i < i:
                return False
        return True

    active: list[CZone] = []
    trades: list[dict] = []
    in_pos_until = -1

    for i in range(120, n):
        # register zones created at previous bar (confirmed)
        for z in zones_by_bar.get(i - 1, []):
            active.append(z)
        # prune old/mitigated
        active = [z for z in active if not z.mitigated and i - z.created_i <= max_zone_age]

        # snapshot mitigation state at bar open (audit fix: the stacked-zone
        # check must not see mitigations that happen at THIS bar's close)
        mit_before = {id(z): z.mitigated for z in active}

        for z in active:
            if i <= z.created_i:
                continue
            height = abs(z.prox_p - z.distal)
            if height <= 0:
                z.mitigated = True
                continue
            sl_level = (z.distal - stop_pct * height) if z.is_demand else (z.distal + stop_pct * height)

            touched = (l[i] <= z.prox_p) if z.is_demand else (h[i] >= z.prox_p)
            if not touched:
                # mitigation on close beyond distal without touch (gap)
                if (z.is_demand and c[i] < z.distal) or ((not z.is_demand) and c[i] > z.distal):
                    z.mitigated = True
                continue

            # penetration of this touch (fraction of zone height beyond proximal)
            if z.is_demand:
                pen = (z.prox_p - l[i]) / height
            else:
                pen = (h[i] - z.prox_p) / height
            pen = max(0.0, pen)

            # was the zone tradeable BEFORE this touch?
            if fresh_mode == "fresh_only":
                tradeable = z.touches == 0
            elif fresh_mode == "user":
                tradeable = z.touches == 0 or (z.touches == 1 and z.max_penetration <= 0.25)
            else:
                tradeable = True

            # stacked-zone rule: if another active same-direction zone overlaps
            # and is deeper (more distal), this zone is skipped
            if tradeable:
                for z2 in active:
                    if z2 is z or mit_before.get(id(z2), z2.mitigated) or z2.is_demand != z.is_demand:
                        continue
                    lo1, hi1 = min(z.prox_p, z.distal), max(z.prox_p, z.distal)
                    lo2, hi2 = min(z2.prox_p, z2.distal), max(z2.prox_p, z2.distal)
                    overlap = hi1 >= lo2 and hi2 >= lo1
                    deeper = (z2.distal < z.distal) if z.is_demand else (z2.distal > z.distal)
                    if overlap and deeper:
                        tradeable = False
                        break

            # gates at the last COMPLETED bar (i-1) — no lookahead
            if tradeable and use_valuation and score_v is not None:
                s = score_v[i - 1]
                if not np.isfinite(s):
                    tradeable = False
                elif z.is_demand and not (s <= -t1):
                    tradeable = False
                elif (not z.is_demand) and not (s >= t1):
                    tradeable = False
            if tradeable and not htf_covered(z, idx[i - 1]):
                tradeable = False
            if tradeable and z.fcode not in formations:
                tradeable = False
            if tradeable and location_gate:
                pos = daily_pos(idx[i - 1], float(c[i - 1]))
                if pos is not None:
                    if z.is_demand and not (pos < 0.33):
                        tradeable = False
                    if (not z.is_demand) and not (pos > 0.66):
                        tradeable = False
            if tradeable and trend_gate and daily_trend is not None and daily_index is not None:
                d_i = daily_index.searchsorted(idx[i - 1].normalize()) - 1
                tr = daily_trend[d_i] if 0 <= d_i < len(daily_trend) else 0
                with_trend = (tr == 1 and z.is_demand) or (tr == -1 and not z.is_demand)
                if not with_trend and tr != 0:
                    # counter-trend only with clean arrival (Bernd rule 4/5.5)
                    if not arrival_clean(z, i):
                        tradeable = False
            if tradeable and arrival_gate and not arrival_clean(z, i):
                tradeable = False
            if tradeable and pm_gate:
                height = abs(z.prox_p - z.distal)
                entry_est = z.prox_p
                risk_est = height * (1.0 + stop_pct)
                headroom = None
                for z2 in active:
                    if z2.is_demand == z.is_demand or mit_before.get(id(z2), z2.mitigated):
                        continue
                    if z.is_demand and z2.prox_p > entry_est:
                        d2 = z2.prox_p - entry_est
                        headroom = d2 if headroom is None else min(headroom, d2)
                    elif (not z.is_demand) and z2.prox_p < entry_est:
                        d2 = entry_est - z2.prox_p
                        headroom = d2 if headroom is None else min(headroom, d2)
                if headroom is not None and headroom < 2.0 * risk_est:
                    tradeable = False

            take = tradeable and i > in_pos_until

            # record the touch AFTER deciding (entry happens on this touch)
            z.touches += 1
            z.max_penetration = max(z.max_penetration, pen)
            if (z.is_demand and c[i] < z.distal) or ((not z.is_demand) and c[i] > z.distal):
                z.mitigated = True

            if not take:
                continue

            entry = z.prox_p + (friction if z.is_demand else -friction)
            risk = abs(entry - sl_level)
            if risk <= 0:
                continue
            tp = entry + (target_r * risk if z.is_demand else -target_r * risk)

            comm_r = 2.0 * cost.commission_pct * entry / risk

            # same-bar violation (touch bar reaches SL) = -1R
            violated = (l[i] <= sl_level) if z.is_demand else (h[i] >= sl_level)
            if violated:
                trades.append({"instrument": name, "ts": idx[i], "side": "long" if z.is_demand else "short",
                               "fcode": z.fcode, "r": -1.0 - comm_r, "bars": 0, "reason": "SAME_BAR_SL",
                               "klass": asset_class(name), "entry": float(entry),
                               "sl": float(sl_level), "tp": float(tp), "entry_i": int(i)})
                in_pos_until = i
                z.mitigated = True
                continue

            # simulate forward: stop-before-target
            r_out, bars_held, reason = None, 0, "EOS"
            for j in range(i + 1, min(n, i + 400)):
                bars_held = j - i
                hit_sl = (l[j] <= sl_level) if z.is_demand else (h[j] >= sl_level)
                hit_tp = (h[j] >= tp) if z.is_demand else (l[j] <= tp)
                if hit_sl:
                    r_out, reason = -1.0, "SL"
                    break
                if hit_tp:
                    r_out, reason = target_r, "TP"
                    break
            if r_out is None:
                last = min(n - 1, i + 399)
                r_out = ((c[last] - entry) / risk) if z.is_demand else ((entry - c[last]) / risk)
                bars_held = last - i
            trades.append({"instrument": name, "ts": idx[i], "side": "long" if z.is_demand else "short",
                           "fcode": z.fcode, "r": float(r_out) - comm_r, "bars": bars_held, "reason": reason,
                           "klass": asset_class(name), "entry": float(entry),
                           "sl": float(sl_level), "tp": float(tp), "entry_i": int(i)})
            in_pos_until = i + max(bars_held, 1)

    return trades


# ─────────────────────────────────────────────────────────────────────
# Daily HTF zones with lifespan (for coverage)
# ─────────────────────────────────────────────────────────────────────
def daily_zones_with_lifespan(df_daily: pd.DataFrame) -> list[CZone]:
    zones = scan_zones(df_daily)
    c = df_daily["close"].to_numpy()
    n = len(df_daily)
    for z in zones:
        end = 10**9
        for j in range(z.created_i + 1, n):
            if (z.is_demand and c[j] < z.distal) or ((not z.is_demand) and c[j] > z.distal):
                end = j
                break
        z.mit_i = end  # type: ignore[attr-defined]
    return zones


def daily_pivot_trend(df_daily: pd.DataFrame, piv_len: int = 5) -> np.ndarray:
    """Causal pivot-structure trend per daily bar (Bernd spec: 2 higher lows +
    higher high = up; 2 lower highs + lower low = down; else sideways).
    A pivot at bar p is only known at p + piv_len (confirmation)."""
    h = df_daily["high"].to_numpy()
    l = df_daily["low"].to_numpy()
    n = len(df_daily)
    trend = np.zeros(n, dtype=int)
    hs: list[float] = []
    ls: list[float] = []
    for i in range(n):
        p = i - piv_len
        if p >= piv_len:
            if h[p] == max(h[p - piv_len:p + piv_len + 1]):
                hs.append(h[p])
            if l[p] == min(l[p - piv_len:p + piv_len + 1]):
                ls.append(l[p])
        up = (len(ls) >= 3 and len(hs) >= 2 and ls[-1] > ls[-2] > ls[-3]
              and hs[-1] > hs[-2])
        dn = (len(hs) >= 3 and len(ls) >= 2 and hs[-1] < hs[-2] < hs[-3]
              and ls[-1] < ls[-2])
        trend[i] = 1 if up else (-1 if dn else 0)
    return trend
