// backtest-engine.js — BacktestEngine + Trade class for Web Worker
// Usage: importScripts('data-loader.js', 'backtest-engine.js')

(function (ctx) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Direction & ExitReason constants
  // ---------------------------------------------------------------------------

  const Direction = Object.freeze({ LONG: 1, SHORT: -1 });
  const ExitReason = Object.freeze({
    SL: 'SL',
    BE_SL: 'BE_SL',
    TRAIL_SL: 'TRAIL_SL',
    TP3: 'TP3',
    TIMEOUT: 'TIMEOUT'
  });

  // ---------------------------------------------------------------------------
  // TradeConfig
  // ---------------------------------------------------------------------------

  class TradeConfig {
    constructor(opts) {
      opts = opts || {};
      this.tp_levels       = opts.tp_levels       || [[1.0, 0.50], [2.0, 0.30], [3.0, 0.20]];
      this.be_after_tp     = opts.be_after_tp     != null ? opts.be_after_tp     : 1;
      this.be_buffer_atr   = opts.be_buffer_atr   != null ? opts.be_buffer_atr   : 0.05;
      this.trail_after_tp  = opts.trail_after_tp  != null ? opts.trail_after_tp  : 2;
      this.trail_distance_atr = opts.trail_distance_atr != null ? opts.trail_distance_atr : 1.0;
      this.max_bars        = opts.max_bars        != null ? opts.max_bars        : 30;
      this.spread_pips     = opts.spread_pips     != null ? opts.spread_pips     : 2.0;
      this.slippage_pips   = opts.slippage_pips   != null ? opts.slippage_pips   : 0.5;
      this.tp_on_close     = opts.tp_on_close     != null ? opts.tp_on_close     : false;
    }
  }

  // ---------------------------------------------------------------------------
  // Trade
  // ---------------------------------------------------------------------------

  class Trade {
    constructor(pair, direction, entryPrice, stopLoss, entryIdx, entryTime, atrAtEntry, tpPrices, signal) {
      this.pair            = pair;
      this.direction       = direction;
      this.entry_price     = entryPrice;
      this.stop_loss       = stopLoss;
      this.risk_distance   = Math.abs(entryPrice - stopLoss);
      this.entry_idx       = entryIdx;
      this.entry_time      = entryTime;
      this.atr_at_entry    = atrAtEntry;
      this.tp_prices       = tpPrices;

      this.exit_price      = 0;
      this.exit_time       = '';
      this.exit_reason     = '';
      this.pnl_r           = 0;

      this.bars_held       = 0;
      this.tps_hit         = 0;
      this.partial_pnls    = [];
      this.remaining_fraction = 1.0;

      this.current_sl      = stopLoss;
      this.trailing_active = false;
      this.trail_extreme   = 0;

      // Preserve signal metadata for analytics
      this.zone_type       = signal && signal.zone_type    ? signal.zone_type    : '';
      this.pattern_type    = signal && signal.pattern_type ? signal.pattern_type : '';
      this.features        = signal && signal.features     ? signal.features     : {};
    }
  }

  // ---------------------------------------------------------------------------
  // BacktestEngine
  // ---------------------------------------------------------------------------

  class BacktestEngine {
    constructor(config, capital, riskPct) {
      this.config          = config || new TradeConfig();
      this.initial_capital = capital != null ? capital : 10000.0;
      this.capital         = this.initial_capital;
      this.risk_pct        = riskPct != null ? riskPct : 0.01;
      this.trades          = [];
    }

    // -----------------------------------------------------------------------
    // run — iterate bars, generate signals, manage open trades
    // -----------------------------------------------------------------------

    run(pair, bars, strategy) {
      const pip = ctx.getPipValue(pair);
      const spreadCost = (this.config.spread_pips + this.config.slippage_pips) * pip;
      let openTrade = null;

      if (typeof strategy.init === 'function') {
        strategy.init(bars);
      }

      for (let i = 1; i < bars.length; i++) {
        const bar  = bars[i];
        const prev = bars[i - 1];
        let closedThisBar = false;

        // --- Manage existing trade ---
        if (openTrade) {
          openTrade.bars_held += 1;
          const result = this._manageTrade(openTrade, bar, i);
          if (result) {
            this._finalizeTrade(openTrade, pair);
            openTrade = null;
            closedThisBar = true;
          }
        }

        // --- Generate new signal ---
        if (openTrade === null && !closedThisBar) {
          const signal = strategy.generateSignal(i, bar, prev);
          if (signal) {
            const direction = signal.direction;
            let entry = signal.entry;
            const sl = signal.stopLoss;
            let rd = Math.abs(entry - sl);

            if (rd < 1e-10) continue;

            // Apply spread/slippage
            if (direction === 1) {
              entry += spreadCost;
            } else {
              entry -= spreadCost;
            }
            rd = Math.abs(entry - sl);

            // Compute TP prices
            const tpPrices = [];
            for (let t = 0; t < this.config.tp_levels.length; t++) {
              const rMult = this.config.tp_levels[t][0];
              if (direction === 1) {
                tpPrices.push(entry + rd * rMult);
              } else {
                tpPrices.push(entry - rd * rMult);
              }
            }

            openTrade = new Trade(
              pair, direction, entry, sl, i,
              bar.dt.toISOString(), bar.atr, tpPrices, signal
            );
          }
        }
      }

      // --- Close remaining trade at last bar ---
      if (openTrade) {
        const lastBar = bars[bars.length - 1];
        openTrade.exit_price  = lastBar.c;
        openTrade.exit_time   = lastBar.dt.toISOString();
        openTrade.exit_reason = ExitReason.TIMEOUT;
        this._calculatePnl(openTrade);
        this._finalizeTrade(openTrade, pair);
      }
    }

    // -----------------------------------------------------------------------
    // _manageTrade — SL / TP / trailing / timeout logic (per bar)
    // -----------------------------------------------------------------------

    _manageTrade(trade, bar, barIdx) {
      const d   = trade.direction;
      const cfg = this.config;

      // --- Check stop-loss ---
      let slHit = false;
      if (d === 1 && bar.l <= trade.current_sl) {
        slHit = true;
        trade.exit_price = trade.current_sl;
      } else if (d === -1 && bar.h >= trade.current_sl) {
        slHit = true;
        trade.exit_price = trade.current_sl;
      }

      if (slHit) {
        trade.exit_time = bar.dt.toISOString();
        if (trade.tps_hit === 0) {
          trade.exit_reason = ExitReason.SL;
        } else if (trade.trailing_active) {
          trade.exit_reason = ExitReason.TRAIL_SL;
        } else {
          trade.exit_reason = ExitReason.BE_SL;
        }
        this._calculatePnl(trade);
        return true;
      }

      // --- Check take-profits ---
      for (let tpIdx = trade.tps_hit; tpIdx < cfg.tp_levels.length; tpIdx++) {
        const rMult    = cfg.tp_levels[tpIdx][0];
        const fraction = cfg.tp_levels[tpIdx][1];
        const tpPrice  = trade.tp_prices[tpIdx];
        let tpHit = false;

        if (!cfg.tp_on_close) {
          if (d === 1 && bar.h >= tpPrice) tpHit = true;
          else if (d === -1 && bar.l <= tpPrice) tpHit = true;
        } else {
          if (d === 1 && bar.c >= tpPrice) tpHit = true;
          else if (d === -1 && bar.c <= tpPrice) tpHit = true;
        }

        if (tpHit) {
          const partialR = rMult * fraction;
          trade.partial_pnls.push(partialR);
          trade.remaining_fraction -= fraction;
          trade.tps_hit = tpIdx + 1;

          // Break-even adjustment
          if (trade.tps_hit === cfg.be_after_tp) {
            const beBuffer = cfg.be_buffer_atr * trade.risk_distance;
            if (d === 1) {
              trade.current_sl = trade.entry_price - beBuffer;
            } else {
              trade.current_sl = trade.entry_price + beBuffer;
            }
          }

          // Trailing activation
          if (trade.tps_hit === cfg.trail_after_tp) {
            trade.trailing_active = true;
            trade.trail_extreme = tpPrice;
          }

          // Final TP hit — close trade
          if (tpIdx === cfg.tp_levels.length - 1) {
            trade.exit_price  = tpPrice;
            trade.exit_time   = bar.dt.toISOString();
            trade.exit_reason = ExitReason.TP3;
            this._calculatePnl(trade);
            return true;
          }
        } else {
          break;
        }
      }

      // --- Trailing stop update ---
      if (trade.trailing_active) {
        const trailDist = cfg.trail_distance_atr * trade.atr_at_entry;
        if (d === 1) {
          trade.trail_extreme = Math.max(trade.trail_extreme, bar.h);
          const newSl = trade.trail_extreme - trailDist;
          trade.current_sl = Math.max(trade.current_sl, newSl);
        } else {
          trade.trail_extreme = Math.min(trade.trail_extreme, bar.l);
          const newSl = trade.trail_extreme + trailDist;
          trade.current_sl = Math.min(trade.current_sl, newSl);
        }
      }

      // --- Timeout ---
      if (trade.bars_held >= cfg.max_bars) {
        trade.exit_price  = bar.c;
        trade.exit_time   = bar.dt.toISOString();
        trade.exit_reason = ExitReason.TIMEOUT;
        this._calculatePnl(trade);
        return true;
      }

      return false;
    }

    // -----------------------------------------------------------------------
    // _calculatePnl — sum partial TPs + remaining fraction at exit price
    // -----------------------------------------------------------------------

    _calculatePnl(trade) {
      let totalR = 0;
      for (let i = 0; i < trade.partial_pnls.length; i++) {
        totalR += trade.partial_pnls[i];
      }
      if (trade.remaining_fraction > 0) {
        let remainingR;
        if (trade.direction === 1) {
          remainingR = ((trade.exit_price - trade.entry_price) / trade.risk_distance) * trade.remaining_fraction;
        } else {
          remainingR = ((trade.entry_price - trade.exit_price) / trade.risk_distance) * trade.remaining_fraction;
        }
        totalR += remainingR;
      }
      trade.pnl_r = totalR;
    }

    // -----------------------------------------------------------------------
    // _finalizeTrade — push to trades array
    // -----------------------------------------------------------------------

    _finalizeTrade(trade, pair) {
      this.trades.push(trade);
    }

    // -----------------------------------------------------------------------
    // getTradeList — return plain objects for serialization
    // -----------------------------------------------------------------------

    getTradeList() {
      return this.trades.map(function (t) {
        return {
          pair:         t.pair,
          direction:    t.direction,
          entry:        t.entry_price,
          sl:           t.stop_loss,
          exit:         t.exit_price,
          entry_time:   t.entry_time,
          exit_time:    t.exit_time,
          exit_reason:  t.exit_reason,
          pnl_r:        Math.round(t.pnl_r * 10000) / 10000,
          tps_hit:      t.tps_hit,
          bars_held:    t.bars_held,
          zone_type:    t.zone_type,
          pattern_type: t.pattern_type,
          features:     t.features
        };
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Expose on self / globalThis
  // ---------------------------------------------------------------------------

  ctx.Direction      = Direction;
  ctx.ExitReason     = ExitReason;
  ctx.TradeConfig    = TradeConfig;
  ctx.Trade          = Trade;
  ctx.BacktestEngine = BacktestEngine;

})(self);
