// data-loader.js — Bar class, indicator computation, data fetching for Web Worker
// Usage: importScripts('data-loader.js') in a Web Worker

(function (ctx) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Bar class
  // ---------------------------------------------------------------------------

  class Bar {
    constructor(time, o, h, l, c) {
      this.time = time;
      this.dt = new Date(time * 1000); // UTC Date
      this.o = o;
      this.h = h;
      this.l = l;
      this.c = c;
      this.body = c - o;
      this.body_abs = Math.abs(c - o);
      this.range = h > l ? h - l : 1e-10;
      this.is_bull = c >= o;
      this.upper_wick = h - Math.max(o, c);
      this.lower_wick = Math.min(o, c) - l;
      this.atr = 0.0;
      this.ema_fast = 0.0;
      this.ema_slow = 0.0;
    }
  }

  // ---------------------------------------------------------------------------
  // Indicator helpers attached to bars (ATR, EMA fast/slow)
  // ---------------------------------------------------------------------------

  function computeIndicators(bars, atrPeriod, emaFastPeriod, emaSlowPeriod) {
    if (typeof atrPeriod === 'undefined') atrPeriod = 14;
    if (typeof emaFastPeriod === 'undefined') emaFastPeriod = 50;
    if (typeof emaSlowPeriod === 'undefined') emaSlowPeriod = 200;

    const n = bars.length;
    if (n < 2) return;

    // --- True Range series ---
    const trs = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const bar = bars[i];
      if (i === 0) {
        trs[i] = bar.range;
      } else {
        const prevC = bars[i - 1].c;
        trs[i] = Math.max(bar.h - bar.l, Math.abs(bar.h - prevC), Math.abs(bar.l - prevC));
      }
    }

    // --- ATR (Wilder's smoothing) ---
    let atr = 0;
    for (let i = 0; i < n; i++) {
      if (i < atrPeriod) {
        // Simple average of TRs seen so far
        let sum = 0;
        for (let j = 0; j <= i; j++) sum += trs[j];
        atr = sum / (i + 1);
      } else {
        atr = (atr * (atrPeriod - 1) + trs[i]) / atrPeriod;
      }
      bars[i].atr = atr;
    }

    // --- EMA fast ---
    const multF = 2.0 / (emaFastPeriod + 1);
    let emaF = bars[0].c;
    for (let i = 0; i < n; i++) {
      emaF = bars[i].c * multF + emaF * (1 - multF);
      bars[i].ema_fast = emaF;
    }

    // --- EMA slow ---
    const multS = 2.0 / (emaSlowPeriod + 1);
    let emaS = bars[0].c;
    for (let i = 0; i < n; i++) {
      emaS = bars[i].c * multS + emaS * (1 - multS);
      bars[i].ema_slow = emaS;
    }
  }

  // ---------------------------------------------------------------------------
  // Pip value helper
  // ---------------------------------------------------------------------------

  const JPY_PAIRS = new Set([
    'USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'NZDJPY', 'CADJPY', 'CHFJPY'
  ]);

  function getPipValue(pair) {
    return JPY_PAIRS.has(pair) ? 0.01 : 0.0001;
  }

  // ---------------------------------------------------------------------------
  // Pair cache
  // ---------------------------------------------------------------------------

  const pairCache = new Map();

  // ---------------------------------------------------------------------------
  // loadPair — fetch gzipped JSON, decompress, parse, build bars
  // ---------------------------------------------------------------------------

  async function loadPair(pairName, dataBaseUrl) {
    // Return from cache if available
    if (pairCache.has(pairName)) {
      return pairCache.get(pairName);
    }

    const url = dataBaseUrl.replace(/\/+$/, '') + '/' + pairName + '.json.gz';
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
    }

    // Decompress gzip using DecompressionStream API
    const ds = new DecompressionStream('gzip');
    const decompressedStream = response.body.pipeThrough(ds);
    const decompressedResponse = new Response(decompressedStream);
    const jsonText = await decompressedResponse.text();
    const rawBars = JSON.parse(jsonText);

    // Build Bar objects from [timestamp, o, h, l, c] arrays
    const bars = new Array(rawBars.length);
    for (let i = 0; i < rawBars.length; i++) {
      const r = rawBars[i];
      bars[i] = new Bar(r[0], r[1], r[2], r[3], r[4]);
    }

    // Compute indicators on the full bar series
    computeIndicators(bars);

    // Cache and return
    pairCache.set(pairName, bars);
    return bars;
  }

  // ---------------------------------------------------------------------------
  // Expose on self / globalThis for Web Worker importScripts()
  // ---------------------------------------------------------------------------

  ctx.Bar = Bar;
  ctx.computeIndicators = computeIndicators;
  ctx.getPipValue = getPipValue;
  ctx.loadPair = loadPair;
  ctx.pairCache = pairCache;

})(self);
