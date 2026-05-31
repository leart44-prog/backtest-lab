#!/usr/bin/env node
/**
 * fetch_dukascopy.mjs — Download OHLC bars from Dukascopy and write them in the
 * gzipped JSON format the backtest-lab dashboard expects.
 *
 * Output (per pair):  ../data/<PAIR>.json.gz   →  JSON array of [unixSeconds, o, h, l, c]
 * Manifest:           ../data/pairs.json        →  rebuilt for the fetched pairs
 *
 * Dukascopy aggregates these bars from raw tick data, so they are far more
 * accurate than broker-specific candles (this is the source Jason recommended
 * in the chat). The default timeframe is H1 — the timeframe Pete's "H1
 * Oscillator" strategy runs on.
 *
 * ── PREREQUISITE ──────────────────────────────────────────────────────────
 * Dukascopy's data host (datafeed.dukascopy.com) must be reachable. Inside a
 * locked-down Claude Code web environment it is blocked by the network policy
 * ("Host not in allowlist"); add datafeed.dukascopy.com to the allowlist (or
 * run this locally) before invoking.
 *
 * ── USAGE ─────────────────────────────────────────────────────────────────
 *   cd tools && npm install
 *   node fetch_dukascopy.mjs                       # all 28 FX pairs, H1, 2013→now
 *   node fetch_dukascopy.mjs --pairs EURUSD,GBPUSD # subset
 *   node fetch_dukascopy.mjs --tf m15 --from 2024-01-01 --to 2024-06-01
 *   node fetch_dukascopy.mjs --price ask
 *
 * Flags:
 *   --pairs   Comma list of pair names (default: all forex pairs below)
 *   --tf      Timeframe: m1 m5 m15 m30 h1 h4 d1 (default: h1)
 *   --from    Start date YYYY-MM-DD (default: 2013-01-01)
 *   --to      End date   YYYY-MM-DD (default: today)
 *   --price   bid | ask (default: bid — the engine adds spread on top)
 *   --out     Output data directory (default: ../data)
 */

import { getHistoricalRates } from 'dukascopy-node';
import { gzipSync } from 'node:zlib';
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// The 28 FX pairs from the original manifest (matches Pete's "28 pairs").
const FOREX_PAIRS = [
  'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD', 'CADCHF', 'CADJPY',
  'CHFJPY', 'EURAUD', 'EURCAD', 'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD',
  'EURUSD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'GBPNZD', 'GBPUSD',
  'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
];

const JPY_PAIRS = new Set([
  'USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'NZDJPY', 'CADJPY', 'CHFJPY',
]);

// ── Parse CLI args ──────────────────────────────────────────────────────────
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) out[a.slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  }
  return out;
}

const args     = parseArgs(process.argv.slice(2));
const pairs    = (args.pairs ? String(args.pairs).split(',') : FOREX_PAIRS).map((p) => p.trim().toUpperCase());
const timeframe = (args.tf || 'h1').toLowerCase();
const priceType = (args.price || 'bid').toLowerCase();
const fromDate = new Date(args.from || '2013-01-01');
const toDate   = new Date(args.to || new Date().toISOString().slice(0, 10));
const outDir   = resolve(__dirname, args.out || '../data');

if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });

console.log(`Dukascopy fetch → ${outDir}`);
console.log(`  pairs:     ${pairs.length} (${pairs.join(', ')})`);
console.log(`  timeframe: ${timeframe}  price: ${priceType}`);
console.log(`  range:     ${fromDate.toISOString().slice(0, 10)} → ${toDate.toISOString().slice(0, 10)}\n`);

// ── Fetch loop ──────────────────────────────────────────────────────────────
const manifest = [];

for (const pair of pairs) {
  const instrument = pair.toLowerCase(); // Dukascopy FX instrument ids are lowercased symbols
  process.stdout.write(`• ${pair} … `);
  try {
    const rows = await getHistoricalRates({
      instrument,
      dates: { from: fromDate, to: toDate },
      timeframe,
      priceType,
      format: 'json',
      volumes: false,
      // batch large ranges so memory + requests stay reasonable
      batchSize: 10,
      pauseBetweenBatchesMs: 500,
    });

    if (!rows || rows.length === 0) {
      console.log('no data (skipped)');
      continue;
    }

    // Convert to [unixSeconds, o, h, l, c]; ensure ascending unique timestamps.
    const bars = rows
      .map((r) => [Math.floor(r.timestamp / 1000), r.open, r.high, r.low, r.close])
      .sort((a, b) => a[0] - b[0]);

    const json = JSON.stringify(bars);
    const gz = gzipSync(Buffer.from(json), { level: 9 });
    writeFileSync(resolve(outDir, `${pair}.json.gz`), gz);

    manifest.push({
      name: pair,
      bars: bars.length,
      from: bars[0][0],
      to: bars[bars.length - 1][0],
      type: 'forex',
      category: 'forex',
      size: gz.length,
      jpy: JPY_PAIRS.has(pair),
      timeframe,
      source: 'dukascopy',
    });

    console.log(`${bars.length} bars → ${(gz.length / 1024).toFixed(0)} KB`);
  } catch (err) {
    console.log(`ERROR: ${err && err.message ? err.message : err}`);
  }
}

// ── Write manifest ──────────────────────────────────────────────────────────
if (manifest.length > 0) {
  manifest.sort((a, b) => a.name.localeCompare(b.name));
  writeFileSync(resolve(outDir, 'pairs.json'), JSON.stringify(manifest, null, 2));
  console.log(`\n✔ Wrote ${manifest.length} pairs + manifest to ${outDir}`);
} else {
  console.log('\n✖ No pairs fetched — nothing written.');
  process.exitCode = 1;
}
