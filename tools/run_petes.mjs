#!/usr/bin/env node
/**
 * run_petes.mjs — Reproduce Pete's per-pair tuned setup on independent Dukascopy
 * H1 data, then test it out-of-sample.
 *
 * Pete's "Backtest_Master_Report_All_12_Pairs" uses, PER PAIR:
 *   - a tuned Stochastic (K period + K slowing),
 *   - a FIXED-pip stop and a FIXED-pip target (hence the big RR ratios).
 * Entry timing here uses the repo's Pullback-in-Trend port (the documented
 * "faithful port of Pete's V3 bot logic"): Stoch reversal out of the extreme,
 * in the EMA-50/200 trend direction, confirmed by HH/LL structure. SL/TP are
 * taken from his per-pair pip table via the engine's fixed_pips mode.
 *
 * NOTE: only Stoch-K / K-slowing / SL / TP are visible in his sheet, so the
 * trend/structure/oversold filters use the strategy defaults. Differences vs
 * his trade count therefore reflect entry-logic divergence, not just data.
 *
 * Usage:
 *   node run_petes.mjs --from 2026-04-27 --to 2026-05-30   # replicate his window
 *   node run_petes.mjs                                      # full history, out-of-sample
 *   node run_petes.mjs --spread 0                           # zero-cost best case
 */

import { readFileSync, existsSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const JS = resolve(ROOT, 'js');
const DATA = resolve(ROOT, 'data');

// ── Pete's per-pair parameters (from the "Pair Parameters" tab) ───────────────
// stochK = Stoch K period, slowing = K slowing, sl/tp in pips.
const PETE = {
  AUDCAD: { stochK: 2, slowing: 9, sl: 6,  tp: 38 },
  AUDCHF: { stochK: 5, slowing: 8, sl: 8,  tp: 32 },
  AUDJPY: { stochK: 7, slowing: 5, sl: 7,  tp: 26 },
  AUDNZD: { stochK: 4, slowing: 5, sl: 8,  tp: 20 },
  AUDUSD: { stochK: 2, slowing: 9, sl: 6,  tp: 29 },
  EURAUD: { stochK: 1, slowing: 9, sl: 6,  tp: 50 },
  EURCHF: { stochK: 4, slowing: 4, sl: 7,  tp: 29 },
  EURGBP: { stochK: 2, slowing: 8, sl: 8,  tp: 23 },
  EURJPY: { stochK: 3, slowing: 9, sl: 9,  tp: 50 },
  EURNZD: { stochK: 6, slowing: 5, sl: 9,  tp: 50 },
  EURUSD: { stochK: 3, slowing: 4, sl: 6,  tp: 47 },
  GBPAUD: { stochK: 4, slowing: 7, sl: 10, tp: 32 },
};

// ── CLI ───────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) out[a.slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  }
  return out;
}
const args = parseArgs(process.argv.slice(2));
const startTime = args.from ? Math.floor(new Date(args.from).getTime() / 1000) : null;
const endTime   = args.to   ? Math.floor(new Date(args.to).getTime()   / 1000) + 86399 : null;
const spreadPips = args.spread != null ? Number(args.spread) : 0.8;

// ── Load browser engine modules into a shared `self` ──────────────────────────
const self = {};
self.self = self;
function loadModule(file) {
  // eslint-disable-next-line no-new-func
  new Function('self', readFileSync(resolve(JS, file), 'utf8'))(self);
}
['data-loader.js', 'backtest-engine.js', 'analytics.js', 'strategy-pullback.js'].forEach(loadModule);

function loadPairLocal(pairName) {
  const path = resolve(DATA, pairName + '.json.gz');
  if (!existsSync(path)) throw new Error('missing data file: ' + path);
  const rawBars = JSON.parse(gunzipSync(readFileSync(path)).toString('utf8'));
  const bars = new Array(rawBars.length);
  for (let i = 0; i < rawBars.length; i++) {
    const r = rawBars[i];
    bars[i] = new self.Bar(r[0], r[1], r[2], r[3], r[4]);
  }
  self.computeIndicators(bars);
  return bars;
}

// ── Run ─────────────────────────────────────────────────────────────────────
const initialCapital = 100000;   // Pete's report sits on a ~100k account
const riskPct = 1;
const riskDecimal = riskPct / 100;

console.log("Pete's setup — fixed-pip SL/TP + per-pair Stoch  •  Dukascopy H1");
console.log(`  window:  ${args.from || '2013-01-01'} → ${args.to || 'today'}  ${startTime ? '(entries gated to window, full warmup)' : '(full out-of-sample history)'}`);
console.log(`  spread:  ${spreadPips} pips   pairs: ${Object.keys(PETE).length}\n`);

const allTrades = [];
let totalPips = 0;
const perPair = {};

for (const [pair, p] of Object.entries(PETE)) {
  const pip = self.getPipValue(pair);
  const strategyParams = {
    stoch_period: p.stochK,
    smooth_k: p.slowing,
    // remaining knobs use the documented Pete-port defaults
  };
  const cfg = {
    fixed_pips: true,
    sl_pips: p.sl,
    tp_pips: p.tp,
    tp_levels: [[p.tp / p.sl, 1.0]], // single full-size target (rMult unused in fixed mode)
    be_after_tp: 99, trail_after_tp: 99, be_buffer_atr: 0,
    max_bars: 500,
    spread_pips: spreadPips, slippage_pips: 0,
    start_time: startTime, end_time: endTime,
  };

  const bars = loadPairLocal(pair);
  const strat = new self.PullbackStrategy(strategyParams);
  strat.init(bars);
  const engine = new self.BacktestEngine(cfg, initialCapital, riskDecimal);
  engine.run(pair, bars, strat);
  const trades = engine.getTradeList();

  // Convert R → pips for this pair (1R = sl_pips). Net of spread already in price.
  let pairPips = 0, wins = 0;
  for (const t of trades) { pairPips += t.pnl_r * p.sl; if (t.pnl_r > 0) wins++; }
  totalPips += pairPips;
  perPair[pair] = { trades: trades.length, wins, pips: pairPips,
                    totalR: trades.reduce((s, t) => s + t.pnl_r, 0) };
  allTrades.push(...trades);
}

const m = self.computeMetrics(allTrades, initialCapital, riskDecimal);
const s = m.summary;
const finalEq = m.equity_curve[m.equity_curve.length - 1] || initialCapital;

console.log('Per pair:');
console.log('  PAIR     trades   win%     pips      R');
for (const [pair, r] of Object.entries(perPair)) {
  const wr = r.trades ? (r.wins / r.trades * 100).toFixed(0) : '0';
  console.log(`  ${pair.padEnd(7)} ${String(r.trades).padStart(5)}   ${wr.padStart(3)}%  ${r.pips.toFixed(1).padStart(8)}  ${r.totalR >= 0 ? '+' : ''}${r.totalR.toFixed(2)}`);
}

console.log('\n══════════════════════════ TOTAL ══════════════════════════');
console.log(`Trades            ${s.total_trades}`);
console.log(`Win rate          ${(s.win_rate * 100).toFixed(1)}%  (${s.wins}W / ${s.losses}L)`);
console.log(`Total pips        ${totalPips >= 0 ? '+' : ''}${totalPips.toFixed(1)}   (avg ${(totalPips / (s.total_trades || 1)).toFixed(2)} pips/trade)`);
console.log(`Total R           ${s.total_r >= 0 ? '+' : ''}${s.total_r}   expectancy ${s.expectancy} R/trade`);
console.log(`Profit factor     ${s.profit_factor}`);
console.log(`Max drawdown      ${s.max_dd_pct}%  (${s.max_dd_r} R)`);
console.log(`Equity (1% risk)  ${initialCapital} → ${finalEq.toFixed(0)}  (${((finalEq / initialCapital - 1) * 100).toFixed(1)}%)`);
console.log('\nExit distribution:');
for (const k of Object.keys(m.exit_distribution).sort()) {
  const e = m.exit_distribution[k];
  console.log(`  ${k.padEnd(9)} ${String(e.count).padStart(6)}   ${e.total_r >= 0 ? '+' : ''}${e.total_r} R`);
}
