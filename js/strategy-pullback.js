// strategy-pullback.js — "Pullbacks within a Trend" strategy (Pete's V3 bot logic, JS port)
// Usage: importScripts('strategy-pullback.js') in a Web Worker
//
// Concept (as described by Pete):
//   "Pull backs within a trend"
//   1) Reversal of the Stochastic oscillator out of an extreme zone (turn back in
//      the trend direction after a counter-trend pullback).
//   2) Price has created a HH (uptrend) / LL (downtrend) to confirm the trend
//      is continuing.
//   => Stoch turn + structure confirmation together trigger the position.
//   TP is taken quick (engine R-multiples / pips), aiming to exit before the next swing.
//
// Designed to be timeframe-agnostic (Pete runs it on an H1 oscillator).
// Trend filter:   EMA fast / slow (default 50 / 200) on the operating timeframe.
// Oscillator:     Stochastic %K (smoothed) and %D.
// Structure:      higher-high (long) / lower-low (short) vs a rolling swing window.
// Entry:          signal-bar close (engine adds spread/slippage).
// Stop:           behind the recent swing low/high +/- ATR buffer (engine derives TP from R).

(function (ctx) {
  'use strict';

  // =========================================================================
  // Default parameters
  // =========================================================================

  var DEFAULTS = {
    // Stochastic oscillator
    stoch_period: 14,
    smooth_k:     3,    // slowing of %K
    smooth_d:     3,    // %D = SMA(slowK, smooth_d)
    oversold:     20,   // long pullback zone
    overbought:   80,   // short pullback zone

    // Trend filter (EMA fast/slow on the operating timeframe)
    ema_fast:        50,
    ema_slow:        200,
    trend_gap_atr:   0.0,  // require |emaFast-emaSlow| >= this * ATR (0 = off)

    // Pullback / reversal detection
    pullback_window: 5,    // %K must have visited the extreme within this many bars
    signal_mode:     'cross_level', // 'cross_level' = %K crosses oversold/overbought,
                                    // 'cross_kd'    = %K crosses %D out of the extreme

    // Structure confirmation (HH / LL)
    require_structure: 1,  // 1 = require HH(long)/LL(short), 0 = oscillator-only
    structure_mode:    'swing', // 'swing'    = market structure shows HH/LL (last pivot vs prev pivot)
                                // 'breakout' = signal bar prints a new high/low vs the prior window
    pivot_lookback:    3,  // fractal half-window for swing-pivot detection ('swing' mode)
    swing_lookback:    10, // prior window used for the broken swing high/low ('breakout' mode)

    // Stop loss
    sl_swing_lookback: 10, // window for the protective swing low/high
    sl_buffer_atr:     0.5 // extra distance beyond the swing extreme (× ATR)
  };

  // =========================================================================
  // Small array helpers
  // =========================================================================

  function _emaArray(bars, period) {
    var n = bars.length;
    var out = new Float64Array(n);
    if (n === 0 || period <= 0) return out;
    var k = 2.0 / (period + 1);
    out[0] = bars[0].c;
    for (var i = 1; i < n; i++) out[i] = bars[i].c * k + out[i - 1] * (1 - k);
    return out;
  }

  function _smaOfSeries(series, period) {
    var n = series.length;
    var out = new Float64Array(n);
    if (n === 0 || period <= 0) return out;
    var sum = 0;
    for (var i = 0; i < n; i++) {
      sum += series[i];
      if (i >= period) sum -= series[i - period];
      out[i] = i >= period - 1 ? sum / period : series[i];
    }
    return out;
  }

  // Raw stochastic %K over `period` (high/low extremes of the window).
  function _rawStoch(bars, period) {
    var n = bars.length;
    var out = new Float64Array(n);
    for (var j = 0; j < n; j++) {
      var start = j - period + 1; if (start < 0) start = 0;
      var hh = bars[start].h, ll = bars[start].l;
      for (var k = start + 1; k <= j; k++) {
        if (bars[k].h > hh) hh = bars[k].h;
        if (bars[k].l < ll) ll = bars[k].l;
      }
      var denom = hh - ll;
      out[j] = denom > 0 ? (bars[j].c - ll) / denom * 100 : 50;
    }
    return out;
  }

  // Rolling max of `high` over the PRIOR window [i-len, i-1] (excludes current bar).
  function _priorHigh(bars, len) {
    var n = bars.length;
    var out = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var start = i - len; if (start < 0) start = 0;
      var mx = -1e99;
      for (var k = start; k < i; k++) if (bars[k].h > mx) mx = bars[k].h;
      out[i] = mx;
    }
    return out;
  }

  function _priorLow(bars, len) {
    var n = bars.length;
    var out = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var start = i - len; if (start < 0) start = 0;
      var mn = 1e99;
      for (var k = start; k < i; k++) if (bars[k].l < mn) mn = bars[k].l;
      out[i] = mn;
    }
    return out;
  }

  // Rolling min/max INCLUDING current bar, used for the protective stop.
  function _swingLow(bars, len) {
    var n = bars.length;
    var out = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var start = i - len + 1; if (start < 0) start = 0;
      var mn = bars[start].l;
      for (var k = start + 1; k <= i; k++) if (bars[k].l < mn) mn = bars[k].l;
      out[i] = mn;
    }
    return out;
  }

  function _swingHigh(bars, len) {
    var n = bars.length;
    var out = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var start = i - len + 1; if (start < 0) start = 0;
      var mx = bars[start].h;
      for (var k = start + 1; k <= i; k++) if (bars[k].h > mx) mx = bars[k].h;
      out[i] = mx;
    }
    return out;
  }

  // Market-structure state via confirmed fractal pivots.
  // A pivot high at index j requires bars[j].h to be the strict max of highs in
  // [j-L, j+L]; it only becomes "known" at bar j+L (no look-ahead).
  // structUp[i]   = true when the last confirmed swing high > the previous one (HH).
  // structDown[i] = true when the last confirmed swing low  < the previous one (LL).
  function _structure(bars, L) {
    var n = bars.length;
    var structUp = new Uint8Array(n);
    var structDown = new Uint8Array(n);

    // Collect pivots with their confirmation bar (idx + L).
    var pivots = []; // { confirm, type:1=high/-1=low, price }
    for (var j = L; j < n - L; j++) {
      var isHigh = true, isLow = true;
      var hj = bars[j].h, lj = bars[j].l;
      for (var k = j - L; k <= j + L; k++) {
        if (k === j) continue;
        if (bars[k].h >= hj) isHigh = false;
        if (bars[k].l <= lj) isLow = false;
        if (!isHigh && !isLow) break;
      }
      if (isHigh) pivots.push({ confirm: j + L, type: 1, price: hj });
      if (isLow)  pivots.push({ confirm: j + L, type: -1, price: lj });
    }
    pivots.sort(function (a, b) { return a.confirm - b.confirm; });

    // Sweep bars, revealing pivots as their confirmation bar passes.
    var pi = 0;
    var lastHigh = null, prevHigh = null, lastLow = null, prevLow = null;
    for (var i = 0; i < n; i++) {
      while (pi < pivots.length && pivots[pi].confirm <= i) {
        var p = pivots[pi++];
        if (p.type === 1) { prevHigh = lastHigh; lastHigh = p.price; }
        else              { prevLow = lastLow;  lastLow = p.price; }
      }
      structUp[i]   = (prevHigh !== null && lastHigh > prevHigh) ? 1 : 0;
      structDown[i] = (prevLow !== null && lastLow < prevLow) ? 1 : 0;
    }
    return { up: structUp, down: structDown };
  }

  // =========================================================================
  // PullbackStrategy
  // =========================================================================

  function PullbackStrategy(params) {
    var cfg = {}, k;
    for (k in DEFAULTS) if (DEFAULTS.hasOwnProperty(k)) cfg[k] = DEFAULTS[k];
    if (params) for (k in params) if (params.hasOwnProperty(k)) cfg[k] = params[k];
    this.cfg  = cfg;
    this.bars = [];
  }

  // -----------------------------------------------------------------------
  // init — precompute oscillator, trend EMAs and swing structure arrays
  // -----------------------------------------------------------------------

  PullbackStrategy.prototype.init = function (bars) {
    var cfg = this.cfg;
    this.bars = bars;

    var rawK     = _rawStoch(bars, cfg.stoch_period);
    this.slowK   = _smaOfSeries(rawK, cfg.smooth_k);
    this.dLine   = _smaOfSeries(this.slowK, cfg.smooth_d);

    this.emaFast = _emaArray(bars, cfg.ema_fast);
    this.emaSlow = _emaArray(bars, cfg.ema_slow);

    this.priorHigh = _priorHigh(bars, cfg.swing_lookback);
    this.priorLow  = _priorLow(bars, cfg.swing_lookback);
    this.slLow     = _swingLow(bars, cfg.sl_swing_lookback);
    this.slHigh    = _swingHigh(bars, cfg.sl_swing_lookback);

    var st = _structure(bars, cfg.pivot_lookback);
    this.structUp   = st.up;
    this.structDown = st.down;

    // Warmup: enough bars for the slowest input to be meaningful.
    this.warmup = Math.max(
      cfg.ema_slow, cfg.stoch_period + cfg.smooth_k + cfg.smooth_d,
      cfg.swing_lookback, cfg.sl_swing_lookback, cfg.pivot_lookback * 2
    ) + 2;
  };

  // -----------------------------------------------------------------------
  // _stochReversal — did %K turn back up (long) / down (short) out of extreme?
  // -----------------------------------------------------------------------

  PullbackStrategy.prototype._reversedUp = function (i) {
    var cfg = this.cfg, K = this.slowK, D = this.dLine;
    // %K must have visited the oversold zone within the pullback window.
    var visited = false;
    for (var b = i - cfg.pullback_window; b <= i; b++) {
      if (b >= 0 && K[b] <= cfg.oversold) { visited = true; break; }
    }
    if (!visited) return false;
    if (cfg.signal_mode === 'cross_kd') {
      return K[i - 1] <= D[i - 1] && K[i] > D[i];
    }
    // cross_level: %K crosses up through the oversold threshold
    return K[i - 1] <= cfg.oversold && K[i] > cfg.oversold;
  };

  PullbackStrategy.prototype._reversedDown = function (i) {
    var cfg = this.cfg, K = this.slowK, D = this.dLine;
    var visited = false;
    for (var b = i - cfg.pullback_window; b <= i; b++) {
      if (b >= 0 && K[b] >= cfg.overbought) { visited = true; break; }
    }
    if (!visited) return false;
    if (cfg.signal_mode === 'cross_kd') {
      return K[i - 1] >= D[i - 1] && K[i] < D[i];
    }
    return K[i - 1] >= cfg.overbought && K[i] < cfg.overbought;
  };

  // -----------------------------------------------------------------------
  // generateSignal — called per bar by the backtest engine
  // -----------------------------------------------------------------------

  PullbackStrategy.prototype.generateSignal = function (i, bar, prev) {
    var cfg = this.cfg;
    var atr = bar.atr;
    if (i < this.warmup || atr < 1e-10) return null;

    // --- Trend filter ---
    var ef = this.emaFast[i], es = this.emaSlow[i];
    var gapOk = cfg.trend_gap_atr <= 0 || Math.abs(ef - es) / atr >= cfg.trend_gap_atr;
    var trend = 0;
    if (ef > es && gapOk) trend = 1;
    else if (ef < es && gapOk) trend = -1;
    if (trend === 0) return null;

    var direction = 0, entry = 0, sl = 0, structOk = false;

    if (trend === 1) {
      // LONG: pullback into oversold, %K turns up, trend structure shows a Higher High.
      if (!this._reversedUp(i)) return null;
      structOk = cfg.structure_mode === 'breakout'
        ? bar.h > this.priorHigh[i]
        : !!this.structUp[i];
      if (cfg.require_structure && !structOk) return null;
      direction = 1;
      entry = bar.c;
      sl    = this.slLow[i] - cfg.sl_buffer_atr * atr;
      if (sl >= entry) return null;
    } else {
      // SHORT: pullback into overbought, %K turns down, trend structure shows a Lower Low.
      if (!this._reversedDown(i)) return null;
      structOk = cfg.structure_mode === 'breakout'
        ? bar.l < this.priorLow[i]
        : !!this.structDown[i];
      if (cfg.require_structure && !structOk) return null;
      direction = -1;
      entry = bar.c;
      sl    = this.slHigh[i] + cfg.sl_buffer_atr * atr;
      if (sl <= entry) return null;
    }

    var rd = Math.abs(entry - sl);
    if (rd < 1e-10) return null;

    var pat = direction === 1 ? 'PB_LONG' : 'PB_SHORT';
    return {
      direction:   direction,
      entry:       entry,
      stopLoss:    sl,
      zoneType:    'pullback',
      patternType: pat,
      features: {
        f_pattern:     pat,
        f_trend:       trend,
        f_stoch_k:     Math.round(this.slowK[i] * 10) / 10,
        f_stoch_d:     Math.round(this.dLine[i] * 10) / 10,
        f_structure:   structOk ? 1 : 0,
        f_signal_mode: cfg.signal_mode,
        f_sl_dist_atr: Math.round(rd / atr * 1000) / 1000
      }
    };
  };

  // =========================================================================
  // Expose
  // =========================================================================

  ctx.PullbackStrategy = PullbackStrategy;
  ctx.PULLBACK_DEFAULTS = DEFAULTS;

})(self);
