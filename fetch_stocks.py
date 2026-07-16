#!/usr/bin/env python3
"""Fetch individual-stock OHLC data via yfinance and write it in the exact
format the Backtest Lab dashboard consumes.

Output (identical shape to build_static_data.py):
  * data/<TICKER>.json.gz  — gzipped JSON list of [timestamp, o, h, l, c]
  * data/pairs.json        — manifest; stock entries are MERGED in (existing
                             forex/futures entries are preserved)

Stocks are stored as DAILY bars, which is the classic Stan Weinstein setup:
a 30-week moving average on daily data is the 150-day MA. The Weinstein-HMM
strategy auto-detects the timeframe (≈5 bars/week for daily), so no manual
tuning is needed.

Usage
-----
  python3 fetch_stocks.py                         # default large-cap basket
  python3 fetch_stocks.py AAPL MSFT NVDA          # explicit tickers
  python3 fetch_stocks.py --period 15y AAPL       # custom look-back
  python3 fetch_stocks.py --interval 1wk AAPL     # weekly bars instead of daily

Requires: pip install yfinance
Note: needs outbound access to Yahoo Finance. Some sandboxed/CI environments
block it by network policy — run this where Yahoo is reachable (e.g. locally).
"""
import os
import sys
import json
import gzip
import argparse

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# A liquid, diversified default basket (Weinstein liked leading stocks in
# leading groups — mostly large-cap trend names across sectors).
DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "HD",
    "AVGO", "COST", "NFLX", "AMD", "CRM",
]


def rows_from_history(df):
    """Convert a yfinance history DataFrame to [[ts, o, h, l, c], ...]."""
    rows = []
    for ts, row in df.iterrows():
        # ts is a pandas Timestamp; store epoch seconds (UTC)
        epoch = int(ts.timestamp())
        o, h, l, c = (
            float(row["Open"]), float(row["High"]),
            float(row["Low"]), float(row["Close"]),
        )
        # skip rows with NaNs / non-finite values
        if not all(map(_finite, (o, h, l, c))):
            continue
        if o > 100:
            o, h, l, c = round(o, 2), round(h, 2), round(l, 2), round(c, 2)
        else:
            o, h, l, c = round(o, 4), round(h, 4), round(l, 4), round(c, 4)
        rows.append([epoch, o, h, l, c])
    rows.sort(key=lambda r: r[0])
    return rows


def _finite(x):
    return x == x and x not in (float("inf"), float("-inf"))


def write_pair(ticker, rows):
    """Compress + write one ticker. Returns the manifest entry (dict)."""
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{ticker}.json.gz")
    payload = json.dumps(rows, separators=(",", ":")).encode("utf-8")
    with gzip.open(out_path, "wb", compresslevel=9) as gz:
        gz.write(payload)
    return {
        "name": ticker,
        "bars": len(rows),
        "from": rows[0][0],
        "to": rows[-1][0],
        "type": "stock",
        "category": "stock",
        "size": os.path.getsize(out_path),
    }


def merge_manifest(new_entries):
    """Merge stock entries into data/pairs.json, replacing same-named entries
    and preserving all existing (forex/futures) instruments."""
    manifest_path = os.path.join(OUT_DIR, "pairs.json")
    existing = []
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            existing = json.load(f)
    by_name = {e["name"]: e for e in existing}
    for e in new_entries:
        by_name[e["name"]] = e
    merged = list(by_name.values())
    with open(manifest_path, "w") as f:
        json.dump(merged, f, indent=2)
    return merged


def fetch(tickers, period, interval):
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance is not installed. Run: pip install yfinance")

    written = []
    for t in tickers:
        t = t.upper().strip()
        if not t:
            continue
        try:
            df = yf.Ticker(t).history(period=period, interval=interval, auto_adjust=True)
        except Exception as exc:  # network/policy/other
            print(f"  {t}: FETCH FAILED — {exc}")
            continue
        if df is None or df.empty:
            print(f"  {t}: no data returned (delisted ticker, or Yahoo unreachable)")
            continue
        rows = rows_from_history(df)
        if len(rows) < 200:
            print(f"  {t}: only {len(rows)} bars — skipping (need history for the 30-week MA)")
            continue
        entry = write_pair(t, rows)
        written.append(entry)
        print(f"  {t}: {entry['bars']} bars, {entry['size']/1024:.0f}KB "
              f"({entry['from']} → {entry['to']})")
    return written


def main():
    ap = argparse.ArgumentParser(description="Fetch stock OHLC for the Backtest Lab.")
    ap.add_argument("tickers", nargs="*", help="Ticker symbols (default: large-cap basket)")
    ap.add_argument("--period", default="max", help="yfinance period (e.g. max, 20y, 10y)")
    ap.add_argument("--interval", default="1d", help="bar interval (1d daily, 1wk weekly)")
    args = ap.parse_args()

    tickers = args.tickers or DEFAULT_TICKERS
    print(f"=== STOCKS ({args.interval}, {args.period}) ===")
    written = fetch(tickers, args.period, args.interval)

    if not written:
        sys.exit("\nNo stock data written. If every ticker failed to fetch, this "
                 "environment likely blocks Yahoo Finance — run where it is reachable.")

    merged = merge_manifest(written)
    total_mb = sum(e["size"] for e in written) / 1024 / 1024
    print(f"\nDone! Added/updated {len(written)} stock(s); manifest now lists "
          f"{len(merged)} instruments ({total_mb:.1f}MB of new stock data).")


if __name__ == "__main__":
    main()
