// analyze_watchlist.js — Weinstein-Analyse einer Watchlist (Cowork-AI-Pipeline)
//
// Zweck: TradingView-Screener liefert Kandidaten → Watchlist hier einfügen →
// die AI zieht Tagesdaten (IBKR MCP oder fetch_stocks.py) und dieses Skript
// klassifiziert jeden Titel nach den Dossier-Regeln:
//   Stage (1-4), Setup-Checks (Stage 1→2 Breakout / armed Retest / Stage-2
//   Pullback), exakte Level (Entry, SL = 1.5×ATR, TP1 2R, TP2 4R) und Ranking.
//
// Eingaben (eine von beiden):
//   node analyze_watchlist.js --bars bars.json
//       bars.json = { "AAPL": [[epochSec,o,h,l,c,vol], ...], "MSFT": [...] }
//       (mind. ~220 Tagesbars pro Ticker; Format von fetch_stocks.py / IBKR-Pull)
//   node analyze_watchlist.js --data <dir> AAPL MSFT HD ...
//       liest <dir>/<TICKER>.json.gz im App-Format (data/-Ordner)
//
// TradingView-Watchlist-Export ("EXCHANGE:SYMBOL,...")-Strings dürfen als
// Ticker-Argumente direkt übergeben werden — Präfixe werden entfernt.

'use strict';
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

// ---------------- Parameter (Dossier-Defaults) ----------------
const P = {
  maLong: 150, maMid: 50, baseLB: 20, volLB: 50, slopeLB: 20,
  volMult: 1.5, freshMax: 60, stopATR: 1.5, atrLB: 14,
  retestValid: 15, pullbackNear: 1.02, matureMin: 25,
};

// ---------------- Indikator-Helfer ----------------
function smaArr(a, p) { const n = a.length, o = new Float64Array(n); let s = 0;
  for (let i = 0; i < n; i++) { s += a[i]; if (i >= p) s -= a[i - p]; o[i] = i >= p - 1 ? s / p : NaN; } return o; }
function atrArr(b, p) { const n = b.length, o = new Float64Array(n); let atr = 0;
  for (let i = 0; i < n; i++) { const tr = i === 0 ? b[i].h - b[i].l :
    Math.max(b[i].h - b[i].l, Math.abs(b[i].h - b[i - 1].c), Math.abs(b[i].l - b[i - 1].c));
    atr = i < p ? (atr * i + tr) / (i + 1) : (atr * (p - 1) + tr) / p; o[i] = atr; } return o; }
function hh(b, from, to) { let m = -Infinity; for (let k = Math.max(0, from); k <= to; k++) if (b[k].h > m) m = b[k].h; return m; }
function ll(b, from, to) { let m = Infinity; for (let k = Math.max(0, from); k <= to; k++) if (b[k].l < m) m = b[k].l; return m; }

// ---------------- Kern: einen Ticker analysieren ----------------
function analyze(ticker, bars) {
  const n = bars.length;
  if (n < P.maLong + P.baseLB + 5) return { ticker, error: `zu wenig Historie (${n} Bars, brauche ≥ ${P.maLong + P.baseLB + 5})` };

  const c = bars.map(x => x.c), v = bars.map(x => x.v || 0);
  const sL = smaArr(c, P.maLong), sM = smaArr(c, P.maMid), aV = smaArr(v, P.volLB), atr = atrArr(bars, P.atrLB);
  const i = n - 1, last = bars[i];

  const slope = (sL[i] - sL[i - P.slopeLB]) / sL[i - P.slopeLB];
  const rising = slope >= 0, above = last.c > sL[i], structure = sM[i] > sL[i];

  // Tage seit Kurs unter der Linie (Freshness/Reife)
  let sinceBelow = 1e9;
  for (let k = i; k >= 0; k--) { if (!isFinite(sL[k]) || c[k] < sL[k]) { sinceBelow = i - k; break; } }

  // Stage-Klassifikation
  let stage, stageTxt;
  if (above && rising && structure) { stage = 2; stageTxt = 'Stage 2 (Aufwärtstrend)'; }
  else if (above && rising) { stage = 2; stageTxt = 'Stage 2 (früh — 50er noch unter 150er)'; }
  else if (!above && !rising) { stage = 4; stageTxt = 'Stage 4 (Abwärtstrend)'; }
  else if (above && !rising) { stage = 1, stageTxt = 'Stage 1 (Basis — Kurs über flacher/fallender Linie)'; }
  else { stage = 3; stageTxt = 'Stage 3/1 (unter steigender Linie — Top oder Re-Basis)'; }

  // Level
  const resist = hh(bars, i - P.baseLB, i - 1);          // Basisdecke (ohne heute)
  const R = P.stopATR * atr[i];
  const distMAPct = (last.c - sL[i]) / sL[i] * 100;
  const volX = aV[i - 1] > 0 ? last.v / aV[i - 1] : 0;

  // Setup-Checks (heutige = letzte geschlossene Kerze)
  const freshOk = sinceBelow <= P.freshMax;
  const volOk = volX >= P.volMult;
  const breakoutToday = above && rising && freshOk && last.c > resist && resist > sL[i];

  // Ausbruch in den letzten retestValid Tagen → Buy-Limit "armed"?
  let armedLevel = null, armedAgo = null;
  for (let k = i; k > i - P.retestValid && k > P.maLong; k--) {
    const rk = hh(bars, k - P.baseLB, k - 1);
    const fOk = (() => { for (let q = k; q >= 0; q--) { if (c[q] < sL[q]) return (k - q) <= P.freshMax; } return false; })();
    if (c[k] > rk && rk > sL[k] && fOk && (v[k] >= P.volMult * (aV[k - 1] || Infinity))) {
      const touched = ll(bars, k + 1, i) <= rk;          // Retest schon passiert?
      if (!touched) { armedLevel = rk; armedAgo = i - k; }
      break;
    }
  }

  // Stage-2-Pullback (Continuation)
  const mature = sinceBelow >= P.matureMin;
  const dipped = ll(bars, i - 7, i - 1) <= sL[i] * P.pullbackNear;
  const reclaim = last.c > sL[i] && last.c > bars[i - 1].c;
  const pullback = stage === 2 && structure && mature && dipped && reclaim;

  // Signal + Level-Vorschlag
  let signal = '—', prio = 9, entry = null;
  if (breakoutToday && volOk) { signal = '🟢 BREAKOUT heute → Buy-Limit-Retest legen'; prio = 1; entry = resist; }
  else if (breakoutToday) { signal = '🟡 Breakout heute, aber Volumen < 1,5×Ø'; prio = 3; entry = resist; }
  else if (armedLevel != null) { signal = `🟢 ARMED: Ausbruch vor ${armedAgo} T — Buy-Limit aktiv halten`; prio = 2; entry = armedLevel; }
  else if (pullback) { signal = '🔵 Stage-2 PULLBACK an die 30W-Linie (Continuation)'; prio = 2; entry = last.c; }
  else if (stage === 2 && freshOk) { signal = 'beobachten: frisches Stage 2, auf Basis/Ausbruch warten'; prio = 4; }
  else if (stage === 2) { signal = 'Stage 2 reif — nur Pullbacks handeln, nicht jagen'; prio = 5; }
  else if (stage === 1) { signal = 'Stage 1 — auf 1→2-Ausbruch warten'; prio = 6; }
  else { signal = stage === 4 ? '⛔ Stage 4 — nicht anfassen (long)' : 'kein Setup'; prio = 8; }

  const out = { ticker, stage, stageTxt, signal, prio,
    close: last.c, date: new Date(last.time * 1000).toISOString().slice(0, 10),
    sma150: sL[i], slopePct: slope * 100, distMAPct, sinceBelow, volX, atr: atr[i] };
  if (entry != null) {
    out.entry = entry; out.sl = entry - R; out.r = R;
    out.tp1 = entry + 2 * R; out.tp2 = entry + 4 * R;
    out.shares1pct = (depot) => Math.floor(depot * 0.01 / R);
  }
  return out;
}

// ---------------- Report ----------------
function fmt(x, d = 2) { return x == null || !isFinite(x) ? '—' : x.toFixed(d); }
function report(results) {
  results.sort((a, b) => (a.prio ?? 9) - (b.prio ?? 9) || (b.slopePct ?? -99) - (a.slopePct ?? -99));
  const lines = [];
  lines.push(`# Weinstein Watchlist-Analyse (${results.length} Titel, Stand ${results.find(r => r.date)?.date || '—'})`);
  lines.push('');
  lines.push('| Ticker | Stage | Signal | Close | Δ150SMA | Slope | Vol×Ø | Entry | SL | TP1 (2R) | TP2 (4R) |');
  lines.push('|--------|-------|--------|-------|---------|-------|-------|-------|-----|----------|----------|');
  for (const r of results) {
    if (r.error) { lines.push(`| ${r.ticker} | — | ⚠️ ${r.error} | | | | | | | | |`); continue; }
    lines.push(`| ${r.ticker} | ${r.stage} | ${r.signal} | ${fmt(r.close)} | ${fmt(r.distMAPct, 1)}% | ${fmt(r.slopePct, 1)}% | ${fmt(r.volX, 1)} | ${fmt(r.entry)} | ${fmt(r.sl)} | ${fmt(r.tp1)} | ${fmt(r.tp2)} |`);
  }
  lines.push('');
  lines.push('Regeln: Entry = Basisdecke (Buy-Limit-Retest) · SL = Entry − 1,5×ATR · Sizing: Stück = 1% Depot ÷ (Entry−SL) · ⛔ Stage 4 nie long.');
  return lines.join('\n');
}

// ---------------- CLI ----------------
function cleanTicker(t) { return t.trim().replace(/^.*:/, '').replace(/,+$/, '').toUpperCase(); }
function main() {
  const args = process.argv.slice(2);
  const barsByTk = {};
  if (args[0] === '--bars') {
    const j = JSON.parse(fs.readFileSync(args[1], 'utf8'));
    for (const [tk, rows] of Object.entries(j))
      barsByTk[cleanTicker(tk)] = rows.map(r => ({ time: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5] || 0 }));
  } else if (args[0] === '--data') {
    const dir = args[1];
    for (const t of args.slice(2).join(',').split(',').map(cleanTicker).filter(Boolean)) {
      const f = path.join(dir, t + '.json.gz');
      if (!fs.existsSync(f)) { barsByTk[t] = null; continue; }
      const rows = JSON.parse(zlib.gunzipSync(fs.readFileSync(f)));
      barsByTk[t] = rows.map(r => ({ time: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5] || 0 }));
    }
  } else {
    console.error('Usage: node analyze_watchlist.js --bars bars.json | --data <dir> TICKER1 TICKER2 ...');
    process.exit(1);
  }
  const results = Object.entries(barsByTk).map(([tk, bars]) =>
    bars ? analyze(tk, bars) : { ticker: tk, error: 'keine Daten gefunden' });
  console.log(report(results));
}

if (require.main === module) main();
module.exports = { analyze, report };
