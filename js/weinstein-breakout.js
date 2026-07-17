// weinstein-breakout.js — Stan Weinstein Stage 1→2 breakout, long-only daily swing
// Usage: importScripts('weinstein-breakout.js') in a Web Worker
//
// The strategy the max-EV optimisation over 498 S&P-500 stocks (2013–2018) selected.
//
// Rules (all SMA-based, long only):
//   * The Weinstein line = 30-week SMA (150-day on daily data). Only trade when it is
//     flat-to-rising (slope ≥ slopeMin) — never buy under a falling MA.
//   * Stage-1 base ceiling = highest high of the last `base_weeks` (default 4w = 20d).
//   * Freshness: only take breakouts where price reclaimed the Weinstein line recently
//     (within `fresh_weeks`) → a genuine Stage 1→2 transition, not a late-stage chase.
//   * Volume confirmation: breakout day volume ≥ volMult × its `vol_weeks` average.
//   * ENTRY — two order styles, both long:
//       - 'limit' (default, best EV): after a confirmed breakout close above the base
//         ceiling *and* the Weinstein line, place a BUY-LIMIT to retest the breakout
//         level; fill on the pullback. Tighter risk → higher expected value.
//       - 'stop': classic BUY-STOP above the base ceiling; fills as price breaks out.
//   * Initial stop = entry − stopATR × ATR (tight, default 1.5). Exits (take-profit /
//     trailing / time) are handled by the backtest engine's Trade Management config.
//
// Timeframe-agnostic: window lengths are given in WEEKS and converted using the
// bars/week auto-detected from the data (daily ≈ 5 → 150-day MA; 4H ≈ 30 → 900 bars).

(function (ctx) {
  'use strict';

  var DEFAULTS = {
    // window lengths in WEEKS (converted to bars via detected bars/week)
    ma_weeks:          30,   // Weinstein 30-week line (150-day on daily)
    mid_weeks:         10,   // shorter SMA (context / optional exits)
    base_weeks:         4,   // Stage-1 base ceiling lookback
    slope_weeks:        4,   // window for the MA-slope measurement
    vol_weeks:         10,   // average-volume window
    fresh_weeks:       12,   // max weeks since price reclaimed the MA (0 = off)
    limit_valid_weeks:  3,   // how long a buy-limit retest order stays live
    // scalars
    entry:        'limit',   // 'limit' (retest, best EV) or 'stop' (breakout)
    slope_min:      0.0,     // min MA slope (fraction over slope window); 0 = flat-to-rising
    buffer:         0.001,   // breakout buffer above the base ceiling
    vol_mult:       1.5,     // breakout volume vs average (0 = no volume filter)
    stop_atr:       1.5,     // initial stop distance in ATR
    cost_pct:       0.001,   // per-entry cost/slippage assumption (fraction)
    auto_bars_per_week: 1,
    bars_per_week:  5        // fallback when auto is off (daily)
  };

  function WeinsteinBreakoutStrategy(params) {
    var cfg = {}, k;
    for (k in DEFAULTS) if (DEFAULTS.hasOwnProperty(k)) cfg[k] = DEFAULTS[k];
    if (params) for (k in params) if (params.hasOwnProperty(k)) cfg[k] = params[k];
    this.cfg = cfg;
    this.sig = null;
  }

  WeinsteinBreakoutStrategy.prototype._detectBpw = function (bars) {
    var n = bars.length;
    if (n < 2) return this.cfg.bars_per_week;
    var weeks = (bars[n - 1].time - bars[0].time) / (7 * 86400);
    if (!(weeks > 0)) return this.cfg.bars_per_week;
    return Math.max(1, Math.min(60, Math.round(n / weeks)));
  };

  function _sma(bars, p) {
    var n = bars.length, out = new Float64Array(n), s = 0;
    for (var i = 0; i < n; i++) {
      s += bars[i].c;
      if (i >= p) s -= bars[i - p].c;
      out[i] = i >= p - 1 ? s / p : NaN;
    }
    return out;
  }
  function _smaVol(bars, p) {
    var n = bars.length, out = new Float64Array(n), s = 0;
    for (var i = 0; i < n; i++) {
      s += bars[i].v;
      if (i >= p) s -= bars[i - p].v;
      out[i] = i >= p - 1 ? s / p : 0;
    }
    return out;
  }
  function _rollMaxHigh(bars, p) {
    var n = bars.length, out = new Float64Array(n);
    for (var i = 0; i < n; i++) {
      var m = -Infinity, st = Math.max(0, i - p + 1);
      for (var k = st; k <= i; k++) if (bars[k].h > m) m = bars[k].h;
      out[i] = m;
    }
    return out;
  }

  WeinsteinBreakoutStrategy.prototype.init = function (bars) {
    var cfg = this.cfg, n = bars.length;
    this.bars = bars;

    var bpw = cfg.auto_bars_per_week ? this._detectBpw(bars) : cfg.bars_per_week;
    this.effBpw = bpw;
    var maP    = Math.max(2, Math.round(cfg.ma_weeks * bpw));
    var baseP  = Math.max(1, Math.round(cfg.base_weeks * bpw));
    var slopeP = Math.max(1, Math.round(cfg.slope_weeks * bpw));
    var volP   = Math.max(1, Math.round(cfg.vol_weeks * bpw));
    var freshP = Math.round(cfg.fresh_weeks * bpw);      // 0 disables
    var limitP = Math.max(1, Math.round(cfg.limit_valid_weeks * bpw));
    this.maP = maP; this.slopeP = slopeP;

    var smaLong = _sma(bars, maP);
    var avgVol  = _smaVol(bars, volP);
    var resist  = _rollMaxHigh(bars, baseP);
    this.smaLong = smaLong;

    // bars since close last below the Weinstein line (freshness of the reclaim)
    var sinceBelow = new Int32Array(n), cnt = 1e9;
    for (var i = 0; i < n; i++) {
      if (!isFinite(smaLong[i])) { sinceBelow[i] = 1e9; continue; }
      if (bars[i].c < smaLong[i]) cnt = 0; else cnt++;
      sinceBelow[i] = cnt;
    }

    this.sig = new Array(n).fill(null);
    var warm = maP + baseP + 2;
    var armUntil = -1, armLevel = 0;
    for (i = warm; i < n; i++) {
      var bar = bars[i];
      if (!isFinite(smaLong[i]) || !isFinite(resist[i - 1]) || bar.atr < 1e-9) continue;
      var slope = (smaLong[i] - smaLong[i - slopeP]) / smaLong[i - slopeP];
      var regimeOk = slope >= cfg.slope_min;
      var freshOk  = freshP <= 0 || sinceBelow[i - 1] <= freshP;
      var level    = resist[i - 1] * (1 + cfg.buffer);
      var volOk    = cfg.vol_mult <= 0 || (avgVol[i - 1] > 0 && bar.v >= cfg.vol_mult * avgVol[i - 1]);

      if (cfg.entry === 'stop') {
        if (regimeOk && freshOk && volOk && bar.h >= level && level > smaLong[i]) {
          var f1 = (bar.o > level ? bar.o : level) * (1 + cfg.cost_pct);
          this.sig[i] = this._mk(f1, bar.atr, slope, sinceBelow[i - 1]);
        }
      } else { // 'limit' — retest of a confirmed breakout
        if (regimeOk && freshOk && volOk && bar.c > level && level > smaLong[i] && i > armUntil) {
          armUntil = i + limitP; armLevel = level;
        }
        if (i <= armUntil && bar.l <= armLevel && bar.c > smaLong[i]) {
          var f2 = (bar.o < armLevel ? bar.o : armLevel) * (1 + cfg.cost_pct);
          this.sig[i] = this._mk(f2, bar.atr, slope, sinceBelow[i - 1]);
          armUntil = -1;
        }
      }
    }
  };

  WeinsteinBreakoutStrategy.prototype._mk = function (entry, atr, slope, since) {
    return {
      direction: 1,
      entry: entry,
      stopLoss: entry - this.cfg.stop_atr * atr,
      zone_type: 'stage2_breakout',
      pattern_type: this.cfg.entry === 'limit' ? 'breakout_retest' : 'breakout_stop',
      features: {
        f_entry:      this.cfg.entry,
        f_ma_slope:   Math.round(slope * 10000) / 100,   // % over the slope window
        f_days_since_reclaim: since >= 1e9 ? -1 : since,
        f_stop_atr:   this.cfg.stop_atr,
        f_bpw:        this.effBpw
      }
    };
  };

  WeinsteinBreakoutStrategy.prototype.generateSignal = function (i) {
    return this.sig ? (this.sig[i] || null) : null;
  };

  // Recommended engine Trade-Management config ("runbig": let winners run — the
  // exit style the optimisation paired with these entries for max EV).
  var RECOMMENDED_EXIT = {
    tp_levels: [[2, 0.3], [4, 0.3], [8, 0.4]],
    be_after_tp: 1, trail_after_tp: 2, trail_distance_atr: 3.0,
    max_bars: 400, spread_pips: 0, slippage_pips: 0
  };

  ctx.WeinsteinBreakoutStrategy = WeinsteinBreakoutStrategy;
  ctx.WEINSTEIN_BREAKOUT_DEFAULTS = DEFAULTS;
  ctx.WEINSTEIN_BREAKOUT_EXIT = RECOMMENDED_EXIT;

})(self);
