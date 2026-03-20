// analytics.js — Portfolio analytics for Web Worker
// Usage: importScripts('data-loader.js', 'backtest-engine.js', 'analytics.js')

(function (ctx) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function round4(v) { return Math.round(v * 10000) / 10000; }
  function round2(v) { return Math.round(v * 100) / 100; }

  function _emptyMetrics() {
    return {
      summary: {
        total_trades: 0, wins: 0, losses: 0, win_rate: 0,
        total_r: 0, avg_r: 0, avg_win_r: 0, avg_loss_r: 0,
        profit_factor: 0, expectancy: 0, sharpe: 0, sortino: 0, calmar: 0,
        max_dd_pct: 0, max_dd_r: 0,
        max_win_streak: 0, max_loss_streak: 0, avg_bars_held: 0,
        profitable_years: 0,
        long_trades: 0, short_trades: 0, long_r: 0, short_r: 0
      },
      equity_curve: [], dd_series: [], cum_r_curve: [],
      monthly: {}, yearly: {}, yearly_full: {},
      pairs: {}, exit_distribution: {}, pattern_distribution: {},
      heatmap: {}, trades: []
    };
  }

  // ---------------------------------------------------------------------------
  // _computeSummary — full metrics for a subset of trades
  // Returns the same shape as the top-level result (minus yearly_full to
  // avoid infinite recursion) so it can be used for per-year breakdowns.
  // ---------------------------------------------------------------------------

  function _computeSummary(trades, initialCapital, riskPct) {
    if (!trades || trades.length === 0) return _emptyMetrics();

    const pnls   = [];
    const wins   = [];
    const losses = [];
    for (let i = 0; i < trades.length; i++) {
      const r = trades[i].pnl_r;
      pnls.push(r);
      if (r > 0) wins.push(trades[i]);
      else losses.push(trades[i]);
    }

    const totalR    = _sum(pnls);
    const grossWin  = wins.length > 0 ? _sumField(wins, 'pnl_r') : 0;
    const grossLoss = losses.length > 0 ? Math.abs(_sumField(losses, 'pnl_r')) : 0.001;

    // --- Equity curve ---
    const equity = [initialCapital];
    for (let i = 0; i < pnls.length; i++) {
      const riskAmt = equity[equity.length - 1] * riskPct;
      equity.push(equity[equity.length - 1] + pnls[i] * riskAmt);
    }

    // --- Drawdown series (%) ---
    let peak = equity[0];
    const ddSeries = [];
    let maxDd = 0.0;
    for (let i = 0; i < equity.length; i++) {
      if (equity[i] > peak) peak = equity[i];
      const dd = peak > 0 ? (peak - equity[i]) / peak : 0;
      ddSeries.push(-dd * 100);
      if (dd > maxDd) maxDd = dd;
    }

    // --- Drawdown in R ---
    let peakR = 0.0, cumR = 0.0, maxDdR = 0.0;
    for (let i = 0; i < pnls.length; i++) {
      cumR += pnls[i];
      if (cumR > peakR) peakR = cumR;
      const ddR = peakR - cumR;
      if (ddR > maxDdR) maxDdR = ddR;
    }

    // --- Cumulative R curve ---
    const cumRCurve = [0];
    let cumulativeR = 0;
    for (let i = 0; i < pnls.length; i++) {
      cumulativeR += pnls[i];
      cumRCurve.push(round4(cumulativeR));
    }

    // --- Sharpe (annualized) ---
    const meanR = totalR / pnls.length;
    let varianceSum = 0;
    for (let i = 0; i < pnls.length; i++) {
      const diff = pnls[i] - meanR;
      varianceSum += diff * diff;
    }
    const stdR = pnls.length > 1 ? Math.sqrt(varianceSum / (pnls.length - 1)) : 0;
    const sharpe = stdR > 0 ? (meanR / stdR) * Math.sqrt(252) : 0;

    // --- Sortino ---
    let downSquareSum = 0;
    for (let i = 0; i < pnls.length; i++) {
      if (pnls[i] < 0) downSquareSum += pnls[i] * pnls[i];
    }
    const downDev = Math.sqrt(downSquareSum / pnls.length);
    const sortino = downDev > 0 ? (meanR / downDev) * Math.sqrt(252) : 0;

    // --- Calmar ---
    const calmar = maxDdR > 0 ? totalR / maxDdR : 0;

    // --- Win/loss streaks ---
    let maxWinStreak = 0, maxLossStreak = 0;
    let curWin = 0, curLoss = 0;
    for (let i = 0; i < pnls.length; i++) {
      if (pnls[i] > 0) {
        curWin++;
        curLoss = 0;
        if (curWin > maxWinStreak) maxWinStreak = curWin;
      } else {
        curLoss++;
        curWin = 0;
        if (curLoss > maxLossStreak) maxLossStreak = curLoss;
      }
    }

    // --- Avg bars held ---
    let totalBars = 0;
    for (let i = 0; i < trades.length; i++) totalBars += trades[i].bars_held;
    const avgBarsHeld = trades.length > 0 ? totalBars / trades.length : 0;

    // --- Long / Short split ---
    let longTrades = 0, shortTrades = 0, longR = 0, shortR = 0;
    for (let i = 0; i < trades.length; i++) {
      if (trades[i].direction === 1) {
        longTrades++;
        longR += trades[i].pnl_r;
      } else {
        shortTrades++;
        shortR += trades[i].pnl_r;
      }
    }

    // --- Exit distribution ---
    const exitDist = {};
    for (let i = 0; i < trades.length; i++) {
      const reason = trades[i].exit_reason;
      if (!exitDist[reason]) exitDist[reason] = { count: 0, total_r: 0 };
      exitDist[reason].count++;
      exitDist[reason].total_r += trades[i].pnl_r;
    }
    for (const key in exitDist) {
      exitDist[key].total_r = round4(exitDist[key].total_r);
    }

    // --- Pattern distribution ---
    const patternDist = {};
    for (let i = 0; i < trades.length; i++) {
      const pt = trades[i].pattern_type || 'unknown';
      if (!patternDist[pt]) patternDist[pt] = { count: 0, total_r: 0, wins: 0 };
      patternDist[pt].count++;
      patternDist[pt].total_r += trades[i].pnl_r;
      if (trades[i].pnl_r > 0) patternDist[pt].wins++;
    }
    for (const key in patternDist) {
      patternDist[key].total_r  = round4(patternDist[key].total_r);
      patternDist[key].win_rate = patternDist[key].count > 0
        ? round4(patternDist[key].wins / patternDist[key].count)
        : 0;
    }

    // --- Pairs breakdown ---
    const pairsMap = {};
    for (let i = 0; i < trades.length; i++) {
      const p = trades[i].pair;
      if (!pairsMap[p]) pairsMap[p] = { count: 0, total_r: 0, wins: 0 };
      pairsMap[p].count++;
      pairsMap[p].total_r += trades[i].pnl_r;
      if (trades[i].pnl_r > 0) pairsMap[p].wins++;
    }
    for (const key in pairsMap) {
      pairsMap[key].total_r  = round4(pairsMap[key].total_r);
      pairsMap[key].win_rate = pairsMap[key].count > 0
        ? round4(pairsMap[key].wins / pairsMap[key].count)
        : 0;
    }

    // --- Avg win / avg loss ---
    const avgWinR  = wins.length > 0 ? _sumField(wins, 'pnl_r') / wins.length : 0;
    const avgLossR = losses.length > 0 ? _sumField(losses, 'pnl_r') / losses.length : 0;

    // --- Expectancy ---
    const winRate    = trades.length > 0 ? wins.length / trades.length : 0;
    const expectancy = (winRate * avgWinR) + ((1 - winRate) * avgLossR);

    return {
      summary: {
        total_trades:    trades.length,
        wins:            wins.length,
        losses:          losses.length,
        win_rate:        round4(winRate),
        total_r:         round4(totalR),
        avg_r:           round4(meanR),
        avg_win_r:       round4(avgWinR),
        avg_loss_r:      round4(avgLossR),
        profit_factor:   round2(grossWin / grossLoss),
        expectancy:      round4(expectancy),
        sharpe:          round2(sharpe),
        sortino:         round2(sortino),
        calmar:          round2(calmar),
        max_dd_pct:      round2(maxDd * 100),
        max_dd_r:        round4(maxDdR),
        max_win_streak:  maxWinStreak,
        max_loss_streak: maxLossStreak,
        avg_bars_held:   round2(avgBarsHeld),
        profitable_years: 0, // filled at top level
        long_trades:     longTrades,
        short_trades:    shortTrades,
        long_r:          round4(longR),
        short_r:         round4(shortR)
      },
      equity_curve:         equity,
      dd_series:            ddSeries,
      cum_r_curve:          cumRCurve,
      monthly:              {},
      yearly:               {},
      yearly_full:          {},
      pairs:                pairsMap,
      exit_distribution:    exitDist,
      pattern_distribution: patternDist,
      heatmap:              {},
      trades:               trades
    };
  }

  // ---------------------------------------------------------------------------
  // computeMetrics — main entry point
  // ---------------------------------------------------------------------------

  function computeMetrics(trades, initialCapital, riskPct) {
    if (initialCapital == null) initialCapital = 10000.0;
    if (riskPct == null) riskPct = 0.01;

    if (!trades || trades.length === 0) return _emptyMetrics();

    // --- Base summary (uses _computeSummary for core math) ---
    const base = _computeSummary(trades, initialCapital, riskPct);

    // --- Monthly breakdown ---
    const monthlyMap = {};  // { 'YYYY-MM': { count, total_r, wins } }
    for (let i = 0; i < trades.length; i++) {
      const t  = trades[i];
      const dt = t.entry_time ? t.entry_time.slice(0, 7) : 'unknown';
      if (!monthlyMap[dt]) monthlyMap[dt] = { count: 0, total_r: 0, wins: 0 };
      monthlyMap[dt].count++;
      monthlyMap[dt].total_r += t.pnl_r;
      if (t.pnl_r > 0) monthlyMap[dt].wins++;
    }
    for (const key in monthlyMap) {
      monthlyMap[key].total_r  = round4(monthlyMap[key].total_r);
      monthlyMap[key].win_rate = monthlyMap[key].count > 0
        ? round4(monthlyMap[key].wins / monthlyMap[key].count)
        : 0;
    }

    // --- Yearly breakdown (simple) ---
    const yearlyMap = {}; // { 'YYYY': { count, total_r, wins } }
    for (let i = 0; i < trades.length; i++) {
      const t  = trades[i];
      const yr = t.entry_time ? t.entry_time.slice(0, 4) : 'unknown';
      if (!yearlyMap[yr]) yearlyMap[yr] = { count: 0, total_r: 0, wins: 0 };
      yearlyMap[yr].count++;
      yearlyMap[yr].total_r += t.pnl_r;
      if (t.pnl_r > 0) yearlyMap[yr].wins++;
    }
    for (const key in yearlyMap) {
      yearlyMap[key].total_r  = round4(yearlyMap[key].total_r);
      yearlyMap[key].win_rate = yearlyMap[key].count > 0
        ? round4(yearlyMap[key].wins / yearlyMap[key].count)
        : 0;
    }

    // --- Yearly full (per-year _computeSummary) ---
    const yearBuckets = {};
    for (let i = 0; i < trades.length; i++) {
      const yr = trades[i].entry_time ? trades[i].entry_time.slice(0, 4) : 'unknown';
      if (!yearBuckets[yr]) yearBuckets[yr] = [];
      yearBuckets[yr].push(trades[i]);
    }
    const yearlyFull = {};
    let profitableYears = 0;
    for (const yr in yearBuckets) {
      yearlyFull[yr] = _computeSummary(yearBuckets[yr], initialCapital, riskPct);
      if (yearlyFull[yr].summary.total_r > 0) profitableYears++;
    }

    // --- Heatmap: month x year grid of total_r ---
    const heatmap = {}; // { 'YYYY': { '01': r, '02': r, ... } }
    for (const key in monthlyMap) {
      const parts = key.split('-');
      if (parts.length < 2) continue;
      const yr = parts[0];
      const mo = parts[1];
      if (!heatmap[yr]) heatmap[yr] = {};
      heatmap[yr][mo] = monthlyMap[key].total_r;
    }

    // --- Assemble final result ---
    base.summary.profitable_years = profitableYears;
    base.monthly     = monthlyMap;
    base.yearly      = yearlyMap;
    base.yearly_full = yearlyFull;
    base.heatmap     = heatmap;
    base.trades      = trades;

    return base;
  }

  // ---------------------------------------------------------------------------
  // Internal sum helpers
  // ---------------------------------------------------------------------------

  function _sum(arr) {
    let s = 0;
    for (let i = 0; i < arr.length; i++) s += arr[i];
    return s;
  }

  function _sumField(arr, field) {
    let s = 0;
    for (let i = 0; i < arr.length; i++) s += arr[i][field];
    return s;
  }

  // ---------------------------------------------------------------------------
  // Expose on self / globalThis
  // ---------------------------------------------------------------------------

  ctx.computeMetrics   = computeMetrics;
  ctx._computeSummary  = _computeSummary;

})(self);
