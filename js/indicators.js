// indicators.js — Full-series indicator computations for the Pine Script parser
// Usage: importScripts('indicators.js') in a Web Worker
// All functions return arrays (or objects of arrays) index-aligned with the bars input.

(function (ctx) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Helper: extract a source series from bars
  // ---------------------------------------------------------------------------

  function _srcArray(bars, src) {
    const n = bars.length;
    const out = new Float64Array(n);
    switch (src) {
      case 'high':  for (let i = 0; i < n; i++) out[i] = bars[i].h; break;
      case 'low':   for (let i = 0; i < n; i++) out[i] = bars[i].l; break;
      case 'open':  for (let i = 0; i < n; i++) out[i] = bars[i].o; break;
      case 'close': // fall through — default
      default:      for (let i = 0; i < n; i++) out[i] = bars[i].c; break;
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // SMA
  // ---------------------------------------------------------------------------

  function computeSMA(bars, period) {
    const n = bars.length;
    const out = new Float64Array(n); // initialised to 0

    if (n === 0 || period <= 0) return out;

    // Running sum for O(n) computation
    let sum = 0;
    for (let j = 0; j < n; j++) {
      sum += bars[j].c;
      if (j < period - 1) {
        // Not enough bars yet — value stays 0
        continue;
      }
      if (j >= period) {
        sum -= bars[j - period].c;
      }
      out[j] = sum / period;
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // EMA
  // ---------------------------------------------------------------------------

  function computeEMA(bars, period) {
    const n = bars.length;
    const out = new Float64Array(n);

    if (n === 0 || period <= 0) return out;

    const k = 2.0 / (period + 1);
    out[0] = bars[0].c;
    for (let j = 1; j < n; j++) {
      out[j] = bars[j].c * k + out[j - 1] * (1 - k);
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Internal: EMA over a raw Float64Array series (used by MACD)
  // ---------------------------------------------------------------------------

  function _emaOfSeries(series, period) {
    const n = series.length;
    const out = new Float64Array(n);
    if (n === 0 || period <= 0) return out;

    const k = 2.0 / (period + 1);
    out[0] = series[0];
    for (let j = 1; j < n; j++) {
      out[j] = series[j] * k + out[j - 1] * (1 - k);
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // RSI (Wilder's smoothing)
  // ---------------------------------------------------------------------------

  function computeRSI(bars, period) {
    const n = bars.length;
    const out = new Float64Array(n);

    if (n === 0 || period <= 0) return out;

    let avgGain = 0;
    let avgLoss = 0;

    for (let j = 0; j < n; j++) {
      if (j === 0) {
        out[j] = 50; // No prior bar to compare — neutral
        continue;
      }

      const change = bars[j].c - bars[j - 1].c;
      const gain = change > 0 ? change : 0;
      const loss = change < 0 ? -change : 0;

      if (j <= period) {
        // Accumulate initial sums
        avgGain += gain;
        avgLoss += loss;

        if (j === period) {
          avgGain /= period;
          avgLoss /= period;
          if (avgLoss === 0) {
            out[j] = 100;
          } else {
            const rs = avgGain / avgLoss;
            out[j] = 100 - 100 / (1 + rs);
          }
        } else {
          out[j] = 50; // Not enough data yet
        }
      } else {
        // Wilder's smoothing
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;

        if (avgLoss === 0) {
          out[j] = 100;
        } else {
          const rs = avgGain / avgLoss;
          out[j] = 100 - 100 / (1 + rs);
        }
      }
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Highest
  // ---------------------------------------------------------------------------

  function computeHighest(bars, period, src) {
    const n = bars.length;
    const out = new Float64Array(n);
    const s = _srcArray(bars, src);

    if (n === 0 || period <= 0) return out;

    for (let j = 0; j < n; j++) {
      if (j < period - 1) {
        // Not enough bars — compute max of what we have
        let mx = s[0];
        for (let k = 1; k <= j; k++) {
          if (s[k] > mx) mx = s[k];
        }
        out[j] = mx;
      } else {
        let mx = s[j - period + 1];
        for (let k = j - period + 2; k <= j; k++) {
          if (s[k] > mx) mx = s[k];
        }
        out[j] = mx;
      }
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Lowest
  // ---------------------------------------------------------------------------

  function computeLowest(bars, period, src) {
    const n = bars.length;
    const out = new Float64Array(n);
    const s = _srcArray(bars, src);

    if (n === 0 || period <= 0) return out;

    for (let j = 0; j < n; j++) {
      if (j < period - 1) {
        let mn = s[0];
        for (let k = 1; k <= j; k++) {
          if (s[k] < mn) mn = s[k];
        }
        out[j] = mn;
      } else {
        let mn = s[j - period + 1];
        for (let k = j - period + 2; k <= j; k++) {
          if (s[k] < mn) mn = s[k];
        }
        out[j] = mn;
      }
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Standard Deviation (population) of close over a rolling window
  // ---------------------------------------------------------------------------

  function computeStdDev(bars, period) {
    const n = bars.length;
    const out = new Float64Array(n);

    if (n === 0 || period <= 0) return out;

    for (let j = 0; j < n; j++) {
      if (j < period - 1) {
        out[j] = 0;
        continue;
      }
      // Compute mean
      let sum = 0;
      const start = j - period + 1;
      for (let k = start; k <= j; k++) {
        sum += bars[k].c;
      }
      const mean = sum / period;

      // Compute population variance
      let variance = 0;
      for (let k = start; k <= j; k++) {
        const diff = bars[k].c - mean;
        variance += diff * diff;
      }
      out[j] = Math.sqrt(variance / period);
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Bollinger Bands
  // ---------------------------------------------------------------------------

  function computeBB(bars, period, mult) {
    const n = bars.length;
    const middle = computeSMA(bars, period);
    const sd = computeStdDev(bars, period);

    const upper = new Float64Array(n);
    const lower = new Float64Array(n);

    for (let j = 0; j < n; j++) {
      upper[j] = middle[j] + mult * sd[j];
      lower[j] = middle[j] - mult * sd[j];
    }

    return { middle: middle, upper: upper, lower: lower };
  }

  // ---------------------------------------------------------------------------
  // MACD
  // ---------------------------------------------------------------------------

  function computeMACD(bars, fast, slow, sig) {
    const n = bars.length;

    const emaFast = computeEMA(bars, fast);
    const emaSlow = computeEMA(bars, slow);

    // MACD line = EMA(fast) - EMA(slow)
    const line = new Float64Array(n);
    for (let j = 0; j < n; j++) {
      line[j] = emaFast[j] - emaSlow[j];
    }

    // Signal line = EMA of MACD line
    const signal = _emaOfSeries(line, sig);

    // Histogram = line - signal
    const hist = new Float64Array(n);
    for (let j = 0; j < n; j++) {
      hist[j] = line[j] - signal[j];
    }

    return { line: line, signal: signal, hist: hist };
  }

  // ---------------------------------------------------------------------------
  // Stochastic Oscillator
  // ---------------------------------------------------------------------------

  function computeStoch(bars, period) {
    const n = bars.length;
    const out = new Float64Array(n);

    if (n === 0 || period <= 0) return out;

    for (let j = 0; j < n; j++) {
      if (j < period - 1) {
        // Use available bars
        let hh = bars[0].h;
        let ll = bars[0].l;
        for (let k = 1; k <= j; k++) {
          if (bars[k].h > hh) hh = bars[k].h;
          if (bars[k].l < ll) ll = bars[k].l;
        }
        const denom = hh - ll;
        out[j] = denom > 0 ? (bars[j].c - ll) / denom * 100 : 50;
      } else {
        const start = j - period + 1;
        let hh = bars[start].h;
        let ll = bars[start].l;
        for (let k = start + 1; k <= j; k++) {
          if (bars[k].h > hh) hh = bars[k].h;
          if (bars[k].l < ll) ll = bars[k].l;
        }
        const denom = hh - ll;
        out[j] = denom > 0 ? (bars[j].c - ll) / denom * 100 : 50;
      }
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Expose on self / globalThis for Web Worker importScripts()
  // ---------------------------------------------------------------------------

  ctx.computeSMA = computeSMA;
  ctx.computeEMA = computeEMA;
  ctx.computeRSI = computeRSI;
  ctx.computeHighest = computeHighest;
  ctx.computeLowest = computeLowest;
  ctx.computeStdDev = computeStdDev;
  ctx.computeBB = computeBB;
  ctx.computeMACD = computeMACD;
  ctx.computeStoch = computeStoch;

})(self);
