"""Data loading and resampling.

Source: gzipped JSON 4H OHLC in ./data/.
We aggregate 4H -> 12H for Monthly Profile, keep 4H for Weekly Profile
(cannot go below 4H with the data we have).
"""
from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


@dataclass
class Instrument:
    name: str
    asset_type: str       # forex / futures
    category: str         # forex / index / commodity / agriculture / fx_future
    tick: float | None
    jpy: bool
    df_4h: pd.DataFrame   # index = UTC timestamp, cols = open/high/low/close
    df_12h: pd.DataFrame


def load_manifest() -> list[dict]:
    with open(os.path.join(DATA_DIR, "pairs.json")) as f:
        return json.load(f)


def load_bars(name: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"{name}.json.gz")
    with gzip.open(path, "rb") as f:
        raw = json.load(f)
    arr = np.array(raw, dtype=float)
    idx = pd.to_datetime(arr[:, 0].astype("int64"), unit="s", utc=True)
    df = pd.DataFrame({
        "open":  arr[:, 1],
        "high":  arr[:, 2],
        "low":   arr[:, 3],
        "close": arr[:, 4],
    }, index=idx)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def resample_12h(df_4h: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 4H -> 12H. Anchored at 00:00 UTC."""
    o = df_4h["open"].resample("12h", origin="epoch").first()
    h = df_4h["high"].resample("12h", origin="epoch").max()
    l = df_4h["low"].resample("12h", origin="epoch").min()
    c = df_4h["close"].resample("12h", origin="epoch").last()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    return out


def load_instrument(meta: dict) -> Instrument:
    df_4h = load_bars(meta["name"])
    df_12h = resample_12h(df_4h)
    return Instrument(
        name=meta["name"],
        asset_type=meta["type"],
        category=meta["category"],
        tick=meta.get("tick"),
        jpy=meta.get("jpy", False),
        df_4h=df_4h,
        df_12h=df_12h,
    )


# ─────────────────────────────────────────────────────────────────────
# Phase 1 instrument scope
# ─────────────────────────────────────────────────────────────────────
# Exclude: agricultural futures (illiquid), duplicate FX futures (Forex spot available)
PHASE1_EXCLUDE = {
    # Agricultural
    "OJ", "SB", "CC", "CT", "ZC", "ZS", "ZW", "ZO", "KC",
    # FX futures duplicates of spot
    "6A", "6B", "6C", "6E", "6J", "6N", "6S",
}


def phase1_instruments() -> list[dict]:
    manifest = load_manifest()
    return [m for m in manifest if m["name"] not in PHASE1_EXCLUDE]
