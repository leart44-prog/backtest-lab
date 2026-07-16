// weinstein-hmm.js — Stan Weinstein Stage Analysis via a Hidden Markov Model
// Usage: importScripts('weinstein-hmm.js') in a Web Worker
//
// Idea
// ----
// Stan Weinstein's "Stage Analysis" (Secrets for Profiting in Bull and Bear
// Markets) splits a market cycle into four *hidden* regimes:
//
//   Stage 1  Basing / accumulation  — sideways after a decline, MA flattening
//   Stage 2  Advancing / mark-up    — uptrend above a *rising* 30-week MA  (BUY)
//   Stage 3  Topping / distribution — sideways after an advance, MA flattening
//   Stage 4  Declining / mark-down  — downtrend below a *falling* MA        (SELL/SHORT)
//
// Those four stages are exactly a hidden-state process with sticky (persistent)
// transitions, which is what a Hidden Markov Model describes. We fit a 4-state
// Gaussian HMM on Weinstein-style observable features and trade the regime
// transitions the model infers.
//
// Lookahead discipline
// --------------------
//  * All emission features (distance to the 30-week MA, MA slope, momentum) use
//    only trailing windows — they are causal.
//  * HMM *parameters* are estimated with Baum-Welch on an initial TRAINING
//    slice of the series only. This is disclosed, not hidden.
//  * The per-bar regime used for trading is the FILTERED posterior
//    P(state_t | observations_1..t) from the scaled/​log forward recursion — it
//    never looks past bar t (no Viterbi/smoothing backward pass on live bars).
//  * By default signals are only emitted AFTER the training window, so reported
//    trades are genuinely out-of-sample.

(function (ctx) {
  'use strict';

  var LOG_2PI = Math.log(2 * Math.PI);
  var NEG_INF = -1e300;

  // =========================================================================
  // Numerical helpers
  // =========================================================================

  function logsumexp(arr) {
    var mx = NEG_INF;
    for (var i = 0; i < arr.length; i++) if (arr[i] > mx) mx = arr[i];
    if (mx === NEG_INF) return NEG_INF;
    var s = 0;
    for (var j = 0; j < arr.length; j++) s += Math.exp(arr[j] - mx);
    return mx + Math.log(s);
  }

  // log N(x | mu, var) for a diagonal-covariance Gaussian over D features
  function logGauss(x, mu, vari) {
    var lp = 0;
    for (var d = 0; d < x.length; d++) {
      var diff = x[d] - mu[d];
      lp += -0.5 * (LOG_2PI + Math.log(vari[d]) + (diff * diff) / vari[d]);
    }
    return lp;
  }

  // =========================================================================
  // Default parameters
  // =========================================================================

  var DEFAULTS = {
    n_states:      4,      // Weinstein's four stages
    auto_bars_per_week: 1, // derive bars/week from the data's timestamps (daily stocks ≈ 5, 4H ≈ 30)
    bars_per_week: 30,     // fallback / manual value when auto is off
    ma_weeks:      30,     // Weinstein's flagship 30-week moving average
    slope_weeks:   5,      // window used to measure the MA's slope
    mom_weeks:     5,      // trailing momentum window
    train_frac:    0.35,   // fraction of series used to fit the HMM
    em_iters:      18,     // Baum-Welch iterations
    var_floor:     1e-3,   // minimum emission variance (prevents collapse)
    trade_out_of_sample: 1,// 1 = only trade after the training window
    require_confirm: 1,    // 1 = require price/MA-slope agreement with the stage
    allow_short:   1,      // 1 = short Stage-4 entries; 0 = long-only (classic stocks)
    sl_atr_mult:   3.0,    // stop distance in ATR from entry
    seed:          12345   // deterministic k-means seeding
  };

  // =========================================================================
  // WeinsteinHMMStrategy
  // =========================================================================

  function WeinsteinHMMStrategy(params) {
    var cfg = {}, k;
    for (k in DEFAULTS) if (DEFAULTS.hasOwnProperty(k)) cfg[k] = DEFAULTS[k];
    if (params) for (k in params) if (params.hasOwnProperty(k)) cfg[k] = params[k];
    this.cfg = cfg;

    this.bars       = [];
    this.ma         = null;   // 30-week MA, causal
    this.stateSeq   = null;   // filtered argmax regime per bar (causal)
    this.longProb   = null;   // filtered P(Stage 2) per bar
    this.shortProb  = null;   // filtered P(Stage 4) per bar
    this.longState  = -1;
    this.shortState = -1;
    this.tradeStart = 0;
    this.warmup     = 0;
    this.fitted     = false;
  }

  // -----------------------------------------------------------------------
  // Window sizes derived from the bar timeframe
  // -----------------------------------------------------------------------

  WeinsteinHMMStrategy.prototype._windows = function () {
    var c = this.cfg;
    var bpw = this.effBpw || c.bars_per_week;   // effBpw set in init() from the data
    return {
      maP:    Math.max(2, Math.round(bpw * c.ma_weeks)),
      slopeP: Math.max(1, Math.round(bpw * c.slope_weeks)),
      momP:   Math.max(1, Math.round(bpw * c.mom_weeks))
    };
  };

  // Derive bars-per-week from calendar span (robust to weekend/holiday gaps):
  // count of bars divided by elapsed weeks. Daily equities ≈ 5, 24h 4H ≈ 30.
  WeinsteinHMMStrategy.prototype._detectBarsPerWeek = function (bars) {
    var n = bars.length;
    if (n < 2) return this.cfg.bars_per_week;
    var span = bars[n - 1].time - bars[0].time;      // seconds
    var weeks = span / (7 * 86400);
    if (!(weeks > 0)) return this.cfg.bars_per_week;
    var bpw = Math.round(n / weeks);
    return Math.max(1, Math.min(60, bpw));
  };

  // -----------------------------------------------------------------------
  // _buildFeatures — causal Weinstein-style observables per bar
  //   f0: (close - MA) / MA           price extension vs the 30-week MA
  //   f1: MA slope over slopeP bars    is the trend line rising or falling?
  //   f2: trailing momentum over momP  confirms the direction of travel
  // Returns { X: [[f0,f1,f2]...], ma: Float64Array, firstValid: idx }
  // -----------------------------------------------------------------------

  WeinsteinHMMStrategy.prototype._buildFeatures = function (bars) {
    var w = this._windows();
    var n = bars.length;
    var ma = new Float64Array(n);

    // Rolling SMA of close (Weinstein's 30-week MA)
    var sum = 0;
    for (var i = 0; i < n; i++) {
      sum += bars[i].c;
      if (i >= w.maP) sum -= bars[i - w.maP].c;
      if (i >= w.maP - 1) ma[i] = sum / w.maP;
      else ma[i] = bars[i].c; // warm-up placeholder, not used for signals
    }

    var firstValid = Math.max(w.maP - 1, w.maP - 1 + w.slopeP, w.momP);
    var X = new Array(n);
    for (var t = 0; t < n; t++) {
      if (t < firstValid || ma[t] <= 0) { X[t] = null; continue; }
      var f0 = (bars[t].c - ma[t]) / ma[t];
      var maPrev = ma[t - w.slopeP];
      var f1 = maPrev > 0 ? (ma[t] - maPrev) / maPrev : 0;
      var cPrev = bars[t - w.momP].c;
      var f2 = cPrev > 0 ? (bars[t].c - cPrev) / cPrev : 0;
      X[t] = [f0, f1, f2];
    }

    return { X: X, ma: ma, firstValid: firstValid };
  };

  // -----------------------------------------------------------------------
  // Standardize feature rows using stats from the training slice only
  // -----------------------------------------------------------------------

  function _standardize(X, idxs, D) {
    var mean = new Float64Array(D), std = new Float64Array(D), cnt = 0, i, d;
    for (i = 0; i < idxs.length; i++) {
      var row = X[idxs[i]];
      for (d = 0; d < D; d++) mean[d] += row[d];
      cnt++;
    }
    if (cnt === 0) cnt = 1;
    for (d = 0; d < D; d++) mean[d] /= cnt;
    for (i = 0; i < idxs.length; i++) {
      var r = X[idxs[i]];
      for (d = 0; d < D; d++) { var df = r[d] - mean[d]; std[d] += df * df; }
    }
    for (d = 0; d < D; d++) std[d] = Math.sqrt(std[d] / cnt) || 1;
    return { mean: mean, std: std };
  }

  function _applyScale(row, sc, D) {
    var out = new Array(D);
    for (var d = 0; d < D; d++) out[d] = (row[d] - sc.mean[d]) / sc.std[d];
    return out;
  }

  // -----------------------------------------------------------------------
  // Deterministic PRNG (mulberry32) for reproducible k-means seeding
  // -----------------------------------------------------------------------

  function _rng(seed) {
    var s = seed >>> 0;
    return function () {
      s |= 0; s = (s + 0x6D2B79F5) | 0;
      var t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // -----------------------------------------------------------------------
  // k-means (few iterations) to initialise HMM emission means
  // Seeds are spread across quantiles of a Weinstein composite (f0 + f1) so the
  // initial clusters already resemble the stage ordering.
  // -----------------------------------------------------------------------

  function _kmeansInit(data, K, D, seed) {
    var N = data.length, i, d, k;

    // order by composite score (extension + slope) and seed at K quantiles
    var order = [];
    for (i = 0; i < N; i++) order.push(i);
    order.sort(function (a, b) {
      return (data[a][0] + data[a][1]) - (data[b][0] + data[b][1]);
    });
    var means = new Array(K);
    for (k = 0; k < K; k++) {
      var q = Math.min(N - 1, Math.floor((k + 0.5) / K * N));
      means[k] = data[order[q]].slice();
    }

    var assign = new Int32Array(N);
    for (var iter = 0; iter < 8; iter++) {
      // assignment
      for (i = 0; i < N; i++) {
        var best = 0, bestDist = Infinity;
        for (k = 0; k < K; k++) {
          var dist = 0;
          for (d = 0; d < D; d++) { var df = data[i][d] - means[k][d]; dist += df * df; }
          if (dist < bestDist) { bestDist = dist; best = k; }
        }
        assign[i] = best;
      }
      // update
      var sums = [], counts = new Float64Array(K);
      for (k = 0; k < K; k++) sums.push(new Float64Array(D));
      for (i = 0; i < N; i++) {
        var a = assign[i]; counts[a]++;
        for (d = 0; d < D; d++) sums[a][d] += data[i][d];
      }
      for (k = 0; k < K; k++) {
        if (counts[k] > 0) for (d = 0; d < D; d++) means[k][d] = sums[k][d] / counts[k];
      }
    }

    // means + per-cluster variance
    var vars = [], cnt2 = new Float64Array(K);
    for (k = 0; k < K; k++) vars.push(new Float64Array(D));
    for (i = 0; i < N; i++) {
      var aa = assign[i]; cnt2[aa]++;
      for (d = 0; d < D; d++) { var e = data[i][d] - means[aa][d]; vars[aa][d] += e * e; }
    }
    for (k = 0; k < K; k++)
      for (d = 0; d < D; d++) vars[k][d] = cnt2[k] > 1 ? vars[k][d] / cnt2[k] : 1;

    return { means: means, vars: vars };
  }

  // -----------------------------------------------------------------------
  // _baumWelch — fit a diagonal-covariance Gaussian HMM in log space
  // Returns { logPi, logA, mu, vari }
  // -----------------------------------------------------------------------

  WeinsteinHMMStrategy.prototype._baumWelch = function (data) {
    var cfg = this.cfg;
    var S = cfg.n_states, D = data[0].length, T = data.length;
    var i, j, t, d;

    var init = _kmeansInit(data, S, D, cfg.seed);
    var mu = init.means, vari = init.vars;
    for (i = 0; i < S; i++)
      for (d = 0; d < D; d++) if (vari[i][d] < cfg.var_floor) vari[i][d] = cfg.var_floor;

    // sticky transitions: strong self-persistence to start (regimes last)
    var A = [], pi = new Float64Array(S);
    for (i = 0; i < S; i++) {
      A.push(new Float64Array(S));
      for (j = 0; j < S; j++) A[i][j] = (i === j) ? 0.92 : 0.08 / (S - 1);
      pi[i] = 1 / S;
    }

    var logB = new Array(T);          // logB[t][j]
    var la = new Array(T), lb = new Array(T);
    for (t = 0; t < T; t++) { logB[t] = new Float64Array(S); la[t] = new Float64Array(S); lb[t] = new Float64Array(S); }

    for (var iter = 0; iter < cfg.em_iters; iter++) {
      var logPi = new Float64Array(S), logA = [];
      for (i = 0; i < S; i++) {
        logPi[i] = Math.log(pi[i] + 1e-300);
        logA.push(new Float64Array(S));
        for (j = 0; j < S; j++) logA[i][j] = Math.log(A[i][j] + 1e-300);
      }

      // emission log-likelihoods
      for (t = 0; t < T; t++)
        for (j = 0; j < S; j++) logB[t][j] = logGauss(data[t], mu[j], vari[j]);

      // forward (log)
      for (j = 0; j < S; j++) la[0][j] = logPi[j] + logB[0][j];
      var tmp = new Float64Array(S);
      for (t = 1; t < T; t++) {
        for (j = 0; j < S; j++) {
          for (i = 0; i < S; i++) tmp[i] = la[t - 1][i] + logA[i][j];
          la[t][j] = logsumexp(tmp) + logB[t][j];
        }
      }
      // backward (log)
      for (j = 0; j < S; j++) lb[T - 1][j] = 0;
      for (t = T - 2; t >= 0; t--) {
        for (i = 0; i < S; i++) {
          for (j = 0; j < S; j++) tmp[j] = logA[i][j] + logB[t + 1][j] + lb[t + 1][j];
          lb[t][i] = logsumexp(tmp);
        }
      }
      var logProb = logsumexp(la[T - 1]);

      // E-step accumulators
      var gammaSum = new Float64Array(S);            // Σ_t γ_t(i), t=0..T-1
      var gammaSumT1 = new Float64Array(S);          // Σ_t γ_t(i), t=0..T-2
      var xiNum = [];                                // Σ_t ξ_t(i,j)
      for (i = 0; i < S; i++) xiNum.push(new Float64Array(S));
      var muNum = []; for (i = 0; i < S; i++) muNum.push(new Float64Array(D));
      var varNum = []; for (i = 0; i < S; i++) varNum.push(new Float64Array(D));
      var gamma0 = new Float64Array(S);

      for (t = 0; t < T; t++) {
        for (i = 0; i < S; i++) {
          var g = Math.exp(la[t][i] + lb[t][i] - logProb);
          if (t === 0) gamma0[i] = g;
          gammaSum[i] += g;
          if (t < T - 1) gammaSumT1[i] += g;
          for (d = 0; d < D; d++) {
            muNum[i][d] += g * data[t][d];
            varNum[i][d] += g * data[t][d] * data[t][d];
          }
        }
        if (t < T - 1) {
          for (i = 0; i < S; i++)
            for (j = 0; j < S; j++)
              xiNum[i][j] += Math.exp(la[t][i] + logA[i][j] + logB[t + 1][j] + lb[t + 1][j] - logProb);
        }
      }

      // M-step
      for (i = 0; i < S; i++) {
        pi[i] = gamma0[i];
        var denomA = gammaSumT1[i] || 1e-300;
        for (j = 0; j < S; j++) A[i][j] = xiNum[i][j] / denomA;
        var denomG = gammaSum[i] || 1e-300;
        for (d = 0; d < D; d++) {
          mu[i][d] = muNum[i][d] / denomG;
          var v = varNum[i][d] / denomG - mu[i][d] * mu[i][d];
          vari[i][d] = v > cfg.var_floor ? v : cfg.var_floor;
        }
      }
    }

    var outLogPi = new Float64Array(S), outLogA = [];
    for (i = 0; i < S; i++) {
      outLogPi[i] = Math.log(pi[i] + 1e-300);
      outLogA.push(new Float64Array(S));
      for (j = 0; j < S; j++) outLogA[i][j] = Math.log(A[i][j] + 1e-300);
    }
    return { logPi: outLogPi, logA: outLogA, mu: mu, vari: vari };
  };

  // -----------------------------------------------------------------------
  // init — build features, fit HMM on the training slice, filter the full
  // series causally, and map states → Weinstein stages.
  // -----------------------------------------------------------------------

  WeinsteinHMMStrategy.prototype.init = function (bars) {
    var cfg = this.cfg;
    this.bars = bars;
    var n = bars.length;

    // Effective bars/week drives the 30-week MA and derived windows.
    this.effBpw = cfg.auto_bars_per_week ? this._detectBarsPerWeek(bars) : cfg.bars_per_week;

    var feat = this._buildFeatures(bars);
    this.ma = feat.ma;
    var X = feat.X, D = 3;
    this.warmup = feat.firstValid;

    // indices with valid features
    var valid = [];
    for (var t = 0; t < n; t++) if (X[t]) valid.push(t);
    if (valid.length < cfg.n_states * 20) { this.fitted = false; return; }

    // training slice = first train_frac of the valid range
    var trainCount = Math.max(cfg.n_states * 15, Math.floor(valid.length * cfg.train_frac));
    if (trainCount > valid.length) trainCount = valid.length;
    var trainIdx = valid.slice(0, trainCount);
    this.tradeStart = cfg.trade_out_of_sample ? valid[Math.min(trainCount, valid.length - 1)] : valid[0];

    // standardize on training stats, fit HMM on training rows
    var sc = _standardize(X, trainIdx, D);
    this.scale = sc;
    var trainData = new Array(trainIdx.length);
    for (var i = 0; i < trainIdx.length; i++) trainData[i] = _applyScale(X[trainIdx[i]], sc, D);

    var model = this._baumWelch(trainData);
    this.model = model;

    // map states → stages by emission means (composite: extension + slope)
    var S = cfg.n_states, composite = new Array(S);
    for (var s = 0; s < S; s++) composite[s] = { s: s, v: model.mu[s][0] + model.mu[s][1] };
    composite.sort(function (a, b) { return b.v - a.v; });
    this.longState = composite[0].s;               // highest extension+slope → Stage 2
    this.shortState = composite[composite.length - 1].s; // lowest → Stage 4

    // causal filtering over the FULL series: filtered posterior P(state_t | o_1..t)
    this.stateSeq  = new Int32Array(n).fill(-1);
    this.longProb  = new Float64Array(n);
    this.shortProb = new Float64Array(n);

    var laPrev = null, tmp = new Float64Array(S), buf = new Float64Array(S);
    for (t = 0; t < n; t++) {
      if (!X[t]) { laPrev = null; continue; }
      var x = _applyScale(X[t], sc, D);
      var la = new Float64Array(S), j, k;
      if (laPrev === null) {
        for (j = 0; j < S; j++) la[j] = model.logPi[j] + logGauss(x, model.mu[j], model.vari[j]);
      } else {
        for (j = 0; j < S; j++) {
          for (k = 0; k < S; k++) tmp[k] = laPrev[k] + model.logA[k][j];
          la[j] = logsumexp(tmp) + logGauss(x, model.mu[j], model.vari[j]);
        }
      }
      // normalize to a filtered posterior
      for (j = 0; j < S; j++) buf[j] = la[j];
      var norm = logsumexp(buf);
      var best = 0, bestP = -Infinity;
      for (j = 0; j < S; j++) {
        var p = Math.exp(la[j] - norm);
        if (p > bestP) { bestP = p; best = j; }
        if (j === this.longState) this.longProb[t] = p;
        if (j === this.shortState) this.shortProb[t] = p;
      }
      this.stateSeq[t] = best;
      laPrev = la;
    }

    this.fitted = true;
  };

  // -----------------------------------------------------------------------
  // generateSignal — long on entry into Stage 2, short on entry into Stage 4
  // -----------------------------------------------------------------------

  WeinsteinHMMStrategy.prototype.generateSignal = function (i, bar, prev) {
    if (!this.fitted) return null;
    if (i < this.warmup + 1 || i < this.tradeStart) return null;
    if (bar.atr < 1e-10) return null;

    var cfg = this.cfg;
    var s = this.stateSeq[i], sPrev = this.stateSeq[i - 1];
    if (s < 0 || sPrev < 0) return null;

    var ma = this.ma[i];
    var slopeUp = ma > this.ma[i - this._windows().slopeP];
    var direction = 0;

    // fresh transition INTO a tradable regime
    if (s === this.longState && sPrev !== this.longState) {
      if (!cfg.require_confirm || (bar.c > ma && slopeUp)) direction = 1;   // Stage 2
    } else if (s === this.shortState && sPrev !== this.shortState) {
      if (cfg.allow_short && (!cfg.require_confirm || (bar.c < ma && !slopeUp))) direction = -1; // Stage 4
    }
    if (direction === 0) return null;

    var entry = bar.c;
    var sl = direction === 1
      ? entry - cfg.sl_atr_mult * bar.atr
      : entry + cfg.sl_atr_mult * bar.atr;
    if (Math.abs(entry - sl) < 1e-10) return null;

    var stage = direction === 1 ? 2 : 4;
    return {
      direction:   direction,
      entry:       entry,
      stopLoss:    sl,
      zone_type:   'stage_' + stage,
      pattern_type: direction === 1 ? 'stage2_advance' : 'stage4_decline',
      features: {
        f_stage:        stage,
        f_state:        s,
        f_long_prob:    Math.round(this.longProb[i] * 1000) / 1000,
        f_short_prob:   Math.round(this.shortProb[i] * 1000) / 1000,
        f_ext_ma_pct:   Math.round((bar.c - ma) / ma * 10000) / 100,
        f_ma_slope_up:  slopeUp ? 1 : 0,
        f_bpw:          this.effBpw,
        f_sl_dist_atr:  Math.round(Math.abs(entry - sl) / bar.atr * 1000) / 1000
      }
    };
  };

  // =========================================================================
  // Expose
  // =========================================================================

  ctx.WeinsteinHMMStrategy = WeinsteinHMMStrategy;
  ctx.WEINSTEIN_HMM_DEFAULTS = DEFAULTS;

})(self);
