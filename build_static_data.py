#!/usr/bin/env python3
"""Build compressed OHLC data bundles for the standalone backtest dashboard.

Reads 4H CSV files (Forex + Futures) and produces gzipped JSON files + a pairs manifest.
Output goes to ./data/ directory.
"""
import os, json, gzip, glob, re

BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Engine", "Chart data"
)
FOREX_DIR = os.path.join(BASE, "Forex Data W D 4H")
FUTURES_DIR = os.path.join(BASE, "Futures")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT_DIR, exist_ok=True)

# Futures display names (ticker -> readable name)
FUTURES_NAMES = {
    # Indices
    'CME_MINI_ES1!': 'ES',   'CME_MINI_NQ1!': 'NQ',
    'CBOT_MINI_YM1!': 'YM',  'CME_MINI_RTY1!': 'RTY',
    'CME_NKD1!': 'NKD',      'EUREX_DLY_FDAX1!': 'DAX',
    # Energies & Metals
    'NYMEX_CL1!': 'CL',      'NYMEX_NG1!': 'NG',
    'COMEX_GC1!': 'GC',      'COMEX_SI1!': 'SI',
    'COMEX_HG1!': 'HG',      'NYMEX_PA1!': 'PA',
    'NYMEX_PL1!': 'PL',
    # Agriculture
    'CBOT_ZC1!': 'ZC',       'CBOT_ZS1!': 'ZS',
    'CBOT_ZW1!': 'ZW',       'CBOT_ZO1!': 'ZO',
    'ICEUS_DLY_CC1!': 'CC',  'ICEUS_DLY_CT1!': 'CT',
    'ICEUS_DLY_OJ1!': 'OJ',  'ICEUS_DLY_SB1!': 'SB',
    'ICEUS_DLY_KC1!': 'KC',
    # FX Futures (Majors)
    'CME_6A1!': '6A',  'CME_6B1!': '6B',  'CME_6C1!': '6C',
    'CME_6E1!': '6E',  'CME_6J1!': '6J',  'CME_6N1!': '6N',
    'CME_6S1!': '6S',
}

# Category mapping
FUTURES_CATEGORIES = {
    'Indices': 'index', 'Energies and Metals': 'commodity',
    'Agricultur': 'agriculture', 'Majors': 'fx_future',
}

# Tick size / point value for pip calculation (used by data-loader)
FUTURES_TICK = {
    'ES': 0.25, 'NQ': 0.25, 'YM': 1, 'RTY': 0.1, 'NKD': 5, 'DAX': 0.5,
    'CL': 0.01, 'NG': 0.001, 'GC': 0.1, 'SI': 0.005, 'HG': 0.0005,
    'PA': 0.05, 'PL': 0.1,
    'ZC': 0.25, 'ZS': 0.25, 'ZW': 0.25, 'ZO': 0.25,
    'CC': 1, 'CT': 0.01, 'OJ': 0.05, 'SB': 0.01, 'KC': 0.05,
    '6A': 0.0001, '6B': 0.0001, '6C': 0.0001, '6E': 0.0001,
    '6J': 0.000001, '6N': 0.0001, '6S': 0.0001,
}


def parse_csv(filepath):
    """Read CSV and return list of [timestamp, o, h, l, c]."""
    bars = []
    with open(filepath, 'r') as f:
        f.readline()  # skip header
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 5:
                continue
            try:
                ts = int(float(parts[0]))
                o = float(parts[1])
                h = float(parts[2])
                l = float(parts[3])
                c = float(parts[4])
            except (ValueError, IndexError):
                continue
            # Round based on magnitude
            if o > 100:
                o, h, l, c = round(o, 2), round(h, 2), round(l, 2), round(c, 2)
            else:
                o, h, l, c = round(o, 6), round(h, 6), round(l, 6), round(c, 6)
            bars.append([ts, o, h, l, c])
    return bars


def write_pair(pair_name, bars, asset_type, category, tick_size=None):
    """Compress and write a single pair. Returns manifest entry."""
    out_path = os.path.join(OUT_DIR, f"{pair_name}.json.gz")
    json_bytes = json.dumps(bars, separators=(',', ':')).encode('utf-8')
    with gzip.open(out_path, 'wb', compresslevel=9) as gz:
        gz.write(json_bytes)

    file_size = os.path.getsize(out_path)
    entry = {
        'name': pair_name,
        'bars': len(bars),
        'from': bars[0][0],
        'to': bars[-1][0],
        'type': asset_type,
        'category': category,
        'size': file_size,
    }
    if pair_name.endswith('JPY') or pair_name == '6J':
        entry['jpy'] = True
    if tick_size is not None:
        entry['tick'] = tick_size

    print(f"  {pair_name}: {len(bars)} bars, {file_size/1024:.0f}KB")
    return entry, file_size


def main():
    pairs_manifest = []
    total_size = 0

    # ── Forex ──
    print("=== FOREX ===")
    pattern = os.path.join(FOREX_DIR, "OANDA_*, 240_*.csv")
    for filepath in sorted(glob.glob(pattern)):
        fname = os.path.basename(filepath)
        m = re.match(r'OANDA_(\w+),\s*240_', fname)
        if not m:
            continue
        pair = m.group(1)
        bars = parse_csv(filepath)
        if not bars:
            continue
        entry, sz = write_pair(pair, bars, 'forex', 'forex')
        entry['jpy'] = pair.endswith('JPY')
        pairs_manifest.append(entry)
        total_size += sz

    # ── Futures ──
    print("\n=== FUTURES ===")
    for subdir, cat in FUTURES_CATEGORIES.items():
        subdir_path = os.path.join(FUTURES_DIR, subdir)
        if not os.path.isdir(subdir_path):
            continue
        print(f"\n--- {subdir} ---")
        # Find all 4H (240) files
        for filepath in sorted(glob.glob(os.path.join(subdir_path, "*, 240_*.csv"))):
            fname = os.path.basename(filepath)
            # Extract ticker: "CME_MINI_ES1!, 240_xxxxx.csv" -> "CME_MINI_ES1!"
            ticker = fname.split(',')[0].strip()
            display = FUTURES_NAMES.get(ticker)
            if not display:
                print(f"  Skipping {ticker} (no display name)")
                continue
            bars = parse_csv(filepath)
            if not bars:
                continue
            tick = FUTURES_TICK.get(display)
            entry, sz = write_pair(display, bars, 'futures', cat, tick)
            pairs_manifest.append(entry)
            total_size += sz

    # ── Write manifest ──
    manifest_path = os.path.join(OUT_DIR, "pairs.json")
    with open(manifest_path, 'w') as f:
        json.dump(pairs_manifest, f, indent=2)

    print(f"\nDone! {len(pairs_manifest)} instruments, {total_size/1024/1024:.1f}MB total")


if __name__ == '__main__':
    main()
