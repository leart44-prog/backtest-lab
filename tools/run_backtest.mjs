#!/usr/bin/env node
/**
 * run_backtest.mjs — Headless runner for the backtest-lab engine.
 *
 * Loads the same browser modules the dashboard's Web Worker uses (they are
 * IIFEs bound to a `self` global), feeds them the local Dukascopy H1 bundles in
 * data/, and runs "Pete's" Pullback-in-Trend strategy across the FX pairs —
 * mirroring runBacktest() in js/worker.js with the dashboard's default config.
 *
 * Usage:
 *   node run_backtest.mjs                      # all forex pairs in pairs.json, default params
 *   node run_backtest.mjs --pairs EURUSD,GBPUSD
 *   node run_backtest.mjs --petes-exit         # single TP 1.0R/100%, no trailing (Pete's quick 1:1)
 *   node run_backtest.mjs --json out.json      # also dump full metrics JSON
 */

import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const JS = resolve(ROOT, 'js');
const DATA = resolve(ROOT, 'data');

// ── CLI ──────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) out[a.slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  }
  return out;
}
const args = parseArgs(process.argv.slice(2));

// ── Load the browser modules into a shared `self` ─────────────────────────────
// Each js/*.js file is an IIFE of the form (function (ctx) { ... })(self);
// We provide `self` as a sandboxed global and evaluate the files in order.
const self = {};
self.self = self;
self.globalThis = self;
function loadModule(file) {
  const src = readFileSync(resolve(JS, file), 'utf8');
  // eslint-disable-next-line no-new-func
  const fn = new Function('self', src);
  fn(self);
}
['data-loader.js', 'backtest-engine.js', 'analytics.js', 'strategy-pullback.js'].forEach(loadModule);

// ── Local loadPair: read gzipped JSON bundles straight from disk ──────────────
function loadPairLocal(pairName) {
  const path = resolve(DATA, pairName + '.json.gz');
  if (!existsSync(path)) throw new Error('missing data file: ' + path);
  const rawBars = JSON.parse(gunzipSync(readFileSync(path)).toString('utf8'));
  const bars = new Array(rawBars.length);
  for (let i = 0; i < rawBars.length; i++) {
    const r = rawBars[i];
    bars[i] = new self.Bar(r[0], r[1], r[2], r[3], r[4]);
  }
  self.computeIndicators(bars); // ATR + EMA 50/200 on the bar objects (matches data-loader)
  return bars;
}

// ── Resolve pair list from manifest (forex only) ──────────────────────────────
const manifest = JSON.parse(readFileSync(resolve(DATA, 'pairs.json'), 'utf8'));
const forexNames = manifest
  .filter((m) => (m.category || m.type) === 'forex')
  .map((m) => m.name);
const pairs = (args.pairs ? String(args.pairs).split(',').map((p) => p.trim().toUpperCase()) : forexNames);

// ── Config (mirrors the dashboard's default form values) ──────────────────────
const petesExit = !!args['petes-exit'];
const tradeConfig = petesExit
  ? {
      tp_levels: [[1.0, 1.0]],          // single quick target, full size
      be_after_tp: 1, be_buffer_atr: 0.1,
      trail_after_tp: 99, trail_distance_atr: 1.0, // never trails
      max_bars: 80, spread_pips: 2.0, slippage_pips: 0.5,
    }
  : {
      tp_levels: [[1.0, 0.50], [2.0, 0.30], [3.0, 0.20]],
      be_after_tp: 1, be_buffer_atr: 0.1,
      trail_after_tp: 2, trail_distance_atr: 1.0,
      max_bars: 80, spread_pips: 2.0, slippage_pips: 0.5,
    };

const strategyParams = {
  stoch_period: 14, smooth_k: 3, smooth_d: 3,
  oversold: 20, overbought: 80,
  ema_fast: 50, ema_slow: 200, trend_gap_atr: 0,
  signal_mode: 'cross_level', pullback_window: 5,
  require_structure: 1, swing_lookback: 10,
  sl_swing_lookback: 10, sl_buffer_atr: 0.5,
};

const initialCapital = 10000;
const riskPct = 1;            // %
const riskDecimal = riskPct / 100;

// ── Run (mirrors worker.runBacktest) ──────────────────────────────────────────
console.log('Backtest — Pullback in Trend (Pete\'s strategy)  •  H1 / Dukascopy');
console.log(`  pairs:   ${pairs.length}`);
console.log(`  exit:    ${petesExit ? 'Pete quick 1:1 (single TP 1.0R/100%, no trail)' : 'default scale-out 1R/2R/3R (50/30/20)'}`);
console.log(`  capital: ${initialCapital}  risk/trade: ${riskPct}%\n`);

const allTrades = [];
const errors = [];
let firstTime = Infinity, lastTime = -Infinity, totalBars = 0;

for (const pairName of pairs) {
  try {
    const bars = loadPairLocal(pairName);
    if (bars.length) {
      totalBars += bars.length;
      firstTime = Math.min(firstTime, bars[0].time);
      lastTime = Math.max(lastTime, bars[bars.length - 1].time);
    }
    const strategy = new self.PullbackStrategy(strategyParams);
    strategy.init(bars);
    const engine = new self.BacktestEngine(tradeConfig, initialCapital, riskDecimal);
    engine.run(pairName, bars, strategy);
    const trades = engine.getTradeList();
    allTrades.push(...trades);
    process.stdout.write(`• ${pairName.padEnd(7)} ${String(bars.length).padStart(7)} bars → ${String(trades.length).padStart(4)} trades\n`);
  } catch (err) {
    errors.push(pairName + ': ' + (err.message || String(err)));
    process.stdout.write(`• ${pairName.padEnd(7)} ERROR: ${err.message || err}\n`);
  }
}

const metrics = self.computeMetrics(allTrades, initialCapital, riskDecimal);
metrics.errors = errors;

// ── Report ────────────────────────────────────────────────────────────────────
const s = metrics.summary;
const pct = (v) => (v * 100).toFixed(1) + '%';
const finalEquity = metrics.equity_curve[metrics.equity_curve.length - 1] || initialCapital;
const fmtDate = (t) => Number.isFinite(t) ? new Date(t * 1000).toISOString().slice(0, 10) : 'n/a';

console.log('\n══════════════════════════ RESULT ══════════════════════════');
console.log(`Period            ${fmtDate(firstTime)} → ${fmtDate(lastTime)}   (${(totalBars).toLocaleString()} H1 bars)`);
console.log(`Total trades      ${s.total_trades}   (long ${s.long_trades} / short ${s.short_trades})`);
console.log(`Win rate          ${pct(s.win_rate)}   (${s.wins}W / ${s.losses}L)`);
console.log(`Total R           ${s.total_r >= 0 ? '+' : ''}${s.total_r}`);
console.log(`Expectancy        ${s.expectancy} R/trade   (avg win ${s.avg_win_r}R, avg loss ${s.avg_loss_r}R)`);
console.log(`Profit factor     ${s.profit_factor}`);
console.log(`Sharpe / Sortino  ${s.sharpe} / ${s.sortino}    Calmar ${s.calmar}`);
console.log(`Max drawdown      ${s.max_dd_pct}%  (${s.max_dd_r} R)`);
console.log(`Streaks           +${s.max_win_streak} / -${s.max_loss_streak}    avg hold ${s.avg_bars_held} bars`);
console.log(`Long R / Short R  ${s.long_r} / ${s.short_r}`);
console.log(`Profitable years  ${s.profitable_years} / ${Object.keys(metrics.yearly_full).length}`);
console.log(`Equity (1% risk)  ${initialCapital} → ${finalEquity.toFixed(0)}  (${((finalEquity / initialCapital - 1) * 100).toFixed(1)}%)`);

console.log('\nExit distribution:');
for (const k of Object.keys(metrics.exit_distribution).sort()) {
  const e = metrics.exit_distribution[k];
  console.log(`  ${k.padEnd(9)} ${String(e.count).padStart(5)}   ${e.total_r >= 0 ? '+' : ''}${e.total_r} R`);
}

console.log('\nBy year:');
for (const yr of Object.keys(metrics.yearly).sort()) {
  const y = metrics.yearly[yr];
  console.log(`  ${yr}   ${String(y.count).padStart(5)} trades   win ${pct(y.win_rate)}   ${y.total_r >= 0 ? '+' : ''}${y.total_r} R`);
}

console.log('\nTop / bottom pairs by R:');
const pairRows = Object.entries(metrics.pairs).sort((a, b) => b[1].total_r - a[1].total_r);
const show = (row) => `  ${row[0].padEnd(7)} ${String(row[1].count).padStart(4)} trades   win ${pct(row[1].win_rate)}   ${row[1].total_r >= 0 ? '+' : ''}${row[1].total_r} R`;
pairRows.slice(0, 5).forEach((r) => console.log(show(r)));
console.log('  ...');
pairRows.slice(-5).forEach((r) => console.log(show(r)));

if (errors.length) {
  console.log('\nErrors:');
  errors.forEach((e) => console.log('  ' + e));
}

if (args.json) {
  const outPath = resolve(process.cwd(), String(args.json));
  writeFileSync(outPath, JSON.stringify(metrics, null, 2));
  console.log(`\nFull metrics JSON → ${outPath}`);
}
