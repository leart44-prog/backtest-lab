// playbook-v5.js — Playbook v4.0 Swingtrading Pattern Zone Strategy (JS port)
// Usage: importScripts('playbook-v5.js') in a Web Worker
//
// Pattern zones ONLY (DBR/RBR/DBD/RBD):
//   - Explosive leg-out: body >= exp_mult * ATR
//   - Decisive leg-in:  body >= legin_mult * ATR
//   - Base: 1-6 small candles (body <= base_body_max * ATR)
//   - Imbalance: leg-out body/range >= imbalance_ratio
//   - Freshness: max 1 touch for entry
//   - Min zone size: width >= min_zone_atr * ATR
//
// Trend: EMA 50/200 with gap >= trend_strength * ATR
// Level on Level: overlapping same-type zones → keep distal
// SL: 33% behind distal zone edge

(function (ctx) {
  'use strict';

  // =========================================================================
  // PatternZone class
  // =========================================================================

  function PatternZone(ztype, top, bottom, barIdx, label, pattern,
                       leginStr, legoutStr, baseBars, imbalance, isBB) {
    this.type            = ztype;       // 1=demand, -1=supply
    this.top             = top;
    this.bottom          = bottom;
    this.bar_idx         = barIdx;
    this.touches         = 0;
    this.is_bb           = !!isBB;
    this.active          = true;
    this.left            = false;
    this.in_zone         = true;
    this.label           = label;
    this.pattern         = pattern;     // 'DBR','RBR','DBD','RBD'
    this.legin_strength  = leginStr;
    this.legout_strength = legoutStr;
    this.base_bars       = baseBars;
    this.imbalance       = imbalance;
    this.bb_overlap      = false;
    this.score           = 0.0;
  }

  PatternZone.prototype.width = function () {
    return this.top - this.bottom;
  };

  // =========================================================================
  // Default parameters
  // =========================================================================

  var DEFAULTS = {
    // Leg-out (explosive candle)
    exp_mult: 1.8,
    legin_mult: 1.0,
    imbalance_ratio: 0.65,

    // Base
    max_base_4h: 6,
    base_body_max: 0.5,

    // Zone size
    min_zone_atr: 0.15,

    // Zone management
    max_touches: 3,
    max_entry_touches: 1,
    max_age: 120,
    min_gap: 3,

    // Level on top of level
    overlap_atr: 1.5,

    // Trend
    trend_strength: 0.5,
    ema_fast: 50,
    ema_slow: 200,

    // SL
    sl_pct: 33.0,

    // BB (Daily) — included for completeness, only active when bb_bars available
    bb_exp_mult: 1.0,
    bb_base_atr: 0.5,
    bb_max_age: 50,
    bb_max_touches: 3,
    bb_max_base: 3,
  };

  // =========================================================================
  // PlaybookV5Strategy
  // =========================================================================

  function PlaybookV5Strategy(params) {
    var cfg = {};
    var k;
    for (k in DEFAULTS) { if (DEFAULTS.hasOwnProperty(k)) cfg[k] = DEFAULTS[k]; }
    if (params) { for (k in params) { if (params.hasOwnProperty(k)) cfg[k] = params[k]; } }
    this.cfg   = cfg;
    this.bars  = [];
    this.zones = [];
  }

  // -----------------------------------------------------------------------
  // init — detect all zones on the bar series
  // -----------------------------------------------------------------------

  PlaybookV5Strategy.prototype.init = function (bars) {
    this.bars  = bars;
    this.zones = [];

    this._detectPatternZones(bars, false);
    this._applyLevelOnLevel();
  };

  // -----------------------------------------------------------------------
  // _hasOverlap — check if a new zone overlaps an existing same-type zone
  // -----------------------------------------------------------------------

  PlaybookV5Strategy.prototype._hasOverlap = function (top, bottom, ztype) {
    for (var i = 0; i < this.zones.length; i++) {
      var z = this.zones[i];
      if (!z.active || z.type !== ztype) continue;
      if (top >= z.bottom && bottom <= z.top) return true;
    }
    return false;
  };

  // -----------------------------------------------------------------------
  // _detectPatternZones — DBR / RBR / DBD / RBD
  // -----------------------------------------------------------------------

  PlaybookV5Strategy.prototype._detectPatternZones = function (bars, isBB) {
    var n = bars.length;
    var cfg = this.cfg;
    var maxBase = cfg.max_base_4h;

    for (var i = 3; i < n; i++) {
      var atr = bars[i].atr;
      if (atr < 1e-10) continue;

      var barI   = bars[i];
      var bodyI  = barI.body_abs;
      var rangeI = barI.range;

      // Current bar = potential leg-out
      var isBullLegout = barI.is_bull && bodyI >= cfg.exp_mult * atr;
      var isBearLegout = !barI.is_bull && bodyI >= cfg.exp_mult * atr;

      if (!isBullLegout && !isBearLegout) continue;

      // Imbalance check on leg-out
      var imb = rangeI > 0 ? bodyI / rangeI : 0;
      if (imb < cfg.imbalance_ratio) continue;

      // Search backward for base + leg-in
      for (var baseLen = 1; baseLen <= maxBase; baseLen++) {
        var leginIdx = i - baseLen - 1;
        if (leginIdx < 0) break;

        // Check all base candles are small
        var baseOk  = true;
        var baseHigh = -1e99;
        var baseLow  =  1e99;
        for (var b = i - baseLen; b < i; b++) {
          var bc = bars[b];
          if (bc.body_abs > cfg.base_body_max * atr) {
            baseOk = false;
            break;
          }
          if (bc.h > baseHigh) baseHigh = bc.h;
          if (bc.l < baseLow)  baseLow  = bc.l;
        }

        if (!baseOk) break; // longer bases will include this big candle

        // Leg-in check: decisive candle
        var legin     = bars[leginIdx];
        var leginBody = legin.body_abs;
        if (leginBody < cfg.legin_mult * atr) continue; // try longer base

        var leginStr  = leginBody / atr;
        var legoutStr = bodyI / atr;

        // Pattern classification
        var pattern = '';
        var ztype   = 0;

        if (isBullLegout) {
          // Bull leg-out → demand zone
          pattern = legin.is_bull ? 'RBR' : 'DBR';
          ztype = 1;
        } else if (isBearLegout) {
          // Bear leg-out → supply zone
          pattern = legin.is_bull ? 'RBD' : 'DBD';
          ztype = -1;
        }

        if (ztype === 0) continue;

        // Zone bounds = base high/low
        var zt = baseHigh;
        var zb = baseLow;
        var zw = zt - zb;

        // Min zone size check
        if (zw < cfg.min_zone_atr * atr) continue;

        // No overlap with same-type zone
        if (this._hasOverlap(zt, zb, ztype)) continue;

        this.zones.push(new PatternZone(
          ztype, zt, zb, i, pattern[0], pattern,
          leginStr, legoutStr, baseLen, imb, isBB
        ));
        break; // use shortest valid base
      }
    }
  };

  // -----------------------------------------------------------------------
  // _applyLevelOnLevel — when zones overlap, keep distal, remove proximal
  // -----------------------------------------------------------------------

  PlaybookV5Strategy.prototype._applyLevelOnLevel = function () {
    var active = [];
    for (var a = 0; a < this.zones.length; a++) {
      if (this.zones[a].active) active.push(this.zones[a]);
    }

    for (var i = 0; i < active.length; i++) {
      var z1 = active[i];
      if (!z1.active) continue;

      for (var j = i + 1; j < active.length; j++) {
        var z2 = active[j];
        if (!z2.active || z1.type !== z2.type) continue;

        // Check proximity
        var gap = 0;
        if (z1.top < z2.bottom) {
          gap = z2.bottom - z1.top;
        } else if (z2.top < z1.bottom) {
          gap = z1.bottom - z2.top;
        }
        // else overlapping → gap = 0

        var refBar = Math.min(Math.max(z1.bar_idx, z2.bar_idx), this.bars.length - 1);
        var atr = this.bars[refBar].atr;
        if (atr < 1e-10) continue;

        if (gap < this.cfg.overlap_atr * atr) {
          // Keep distal, remove proximal
          if (z1.type === 1) { // demand: distal = lower
            if (z1.bottom < z2.bottom) z2.active = false;
            else                        z1.active = false;
          } else { // supply: distal = higher
            if (z1.top > z2.top) z2.active = false;
            else                  z1.active = false;
          }
        }
      }
    }
  };

  // -----------------------------------------------------------------------
  // generateSignal — called per bar by the backtest engine
  // -----------------------------------------------------------------------

  PlaybookV5Strategy.prototype.generateSignal = function (i, bar, prev) {
    if (bar.atr < 1e-10 || i < 200) return null;

    var cfg = this.cfg;
    var atr = bar.atr;

    // Trend (EMA 50/200)
    var emaGap    = bar.ema_fast - bar.ema_slow;
    var emaGapAtr = Math.abs(emaGap) / atr;
    var tOk       = cfg.trend_strength === 0 || emaGapAtr >= cfg.trend_strength;
    var trend     = 0;
    if (bar.ema_fast > bar.ema_slow && tOk)      trend = 1;
    else if (bar.ema_fast < bar.ema_slow && tOk)  trend = -1;

    // Update zones + find best signal
    var bestZ     = null;
    var bestScore = -1;

    for (var zi = 0; zi < this.zones.length; zi++) {
      var z = this.zones[zi];
      if (!z.active) continue;

      var age  = i - z.bar_idx;
      var maxA = z.is_bb ? (cfg.bb_max_age * 6) : cfg.max_age;
      var maxT = z.is_bb ? cfg.bb_max_touches : cfg.max_touches;

      // Expire
      if (age > maxA) {
        z.active = false;
        continue;
      }

      // Mitigation
      if (age > cfg.min_gap) {
        if (z.type === 1 && bar.c < z.bottom) { z.active = false; continue; }
        if (z.type === -1 && bar.c > z.top)   { z.active = false; continue; }
      }

      // Zone state machine
      if (age > 0) {
        var pin = bar.l <= z.top && bar.h >= z.bottom;

        if (!z.left) {
          if (!pin && age >= cfg.min_gap) {
            z.left    = true;
            z.in_zone = false;
          }
        } else {
          if (pin && !z.in_zone) {
            z.touches += 1;
            z.in_zone = true;
            if (z.touches > maxT) {
              z.active = false;
              continue;
            }
          } else if (!pin && z.in_zone) {
            z.in_zone = false;
          }
        }

        // Signal check: fresh zone, left, touched, trend alignment
        if (z.active && z.left && pin && z.touches <= cfg.max_entry_touches) {
          if ((z.type === 1 && trend === 1) || (z.type === -1 && trend === -1)) {
            var sc = 0.0;
            if (z.is_bb)        sc += 15;
            if (z.bb_overlap)   sc += 10;
            sc += Math.min(z.legout_strength, 5) * 2;  // explosive leg-out
            sc += Math.min(z.legin_strength, 3) * 1;   // decisive leg-in
            if (z.touches === 0) sc += 5;               // fresh
            if (z.imbalance >= 0.7) sc += 3;            // clean imbalance
            sc += Math.min(z.base_bars, 4) * 0.5;      // base definition

            if (sc > bestScore) {
              bestScore = sc;
              bestZ     = z;
            }
          }
        }
      }
    }

    if (bestZ === null) return null;

    var z      = bestZ;
    var zoneW  = z.width();
    var direction, entry, sl;

    if (z.type === 1) {
      direction = 1;     // LONG
      entry     = z.top;                                       // proximal edge
      sl        = z.bottom - (cfg.sl_pct / 100.0) * zoneW;    // 33% behind distal
    } else {
      direction = -1;    // SHORT
      entry     = z.bottom;                                    // proximal edge
      sl        = z.top + (cfg.sl_pct / 100.0) * zoneW;
    }

    var rd = Math.abs(entry - sl);
    if (rd < 1e-10) return null;

    return {
      direction:   direction,
      entry:       entry,
      stopLoss:    sl,
      zoneType:    z.is_bb ? 'bb_pattern' : (z.bb_overlap ? 'bb_overlap' : 'pattern'),
      patternType: z.pattern,
      features: {
        f_pattern:     z.pattern,
        f_legout_str:  Math.round(z.legout_strength * 100) / 100,
        f_legin_str:   Math.round(z.legin_strength * 100) / 100,
        f_imbalance:   Math.round(z.imbalance * 100) / 100,
        f_base_bars:   z.base_bars,
        f_zone_w_atr:  Math.round(zoneW / atr * 1000) / 1000,
        f_sl_dist_atr: Math.round(rd / atr * 1000) / 1000,
        f_age:         i - z.bar_idx,
        f_bb:          z.is_bb,
        f_bb_overlap:  z.bb_overlap,
        f_touches:     z.touches,
        f_score:       Math.round(bestScore * 10) / 10,
      }
    };
  };

  // =========================================================================
  // Expose
  // =========================================================================

  ctx.PlaybookV5Strategy = PlaybookV5Strategy;
  ctx.PLAYBOOK_V5_DEFAULTS = DEFAULTS;

})(self);
