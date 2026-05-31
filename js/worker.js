/**
 * Web Worker for running backtests in background.
 * Imports all computation modules and communicates via postMessage.
 */

const _v = '?v=3';
importScripts(
    'data-loader.js' + _v,
    'indicators.js' + _v,
    'pine-parser.js' + _v,
    'backtest-engine.js' + _v,
    'analytics.js' + _v,
    'playbook-v5.js' + _v,
    'strategy-pullback.js' + _v
);

// Data base URL (set by main thread)
let dataBaseUrl = './data';

self.onmessage = async function(e) {
    const msg = e.data;

    if (msg.type === 'setBaseUrl') {
        dataBaseUrl = msg.url;
        return;
    }

    if (msg.type === 'run') {
        try {
            await runBacktest(msg);
        } catch (err) {
            self.postMessage({ type: 'error', error: err.message || String(err) });
        }
        return;
    }
};

async function runBacktest(msg) {
    const { pairs, pineCode, strategyType, strategyParams, tradeConfig, initialCapital = 10000, riskPct = 1 } = msg;
    const riskDecimal = riskPct / 100;

    // 1. Build trade config
    const cfg = Object.assign({
        tp_levels: [[1.0, 0.50], [2.0, 0.30], [3.0, 0.20]],
        be_after_tp: 1,
        be_buffer_atr: 0.05,
        trail_after_tp: 2,
        trail_distance_atr: 1.0,
        max_bars: 30,
        spread_pips: 2.0,
        slippage_pips: 0.5,
        tp_on_close: false,
    }, tradeConfig || {});

    if (cfg.tp_levels && Array.isArray(cfg.tp_levels[0])) {
        cfg.tp_levels = cfg.tp_levels.map(l => [Number(l[0]), Number(l[1])]);
    }

    // 2. Determine strategy type
    const usePlaybook = strategyType === 'playbook_v5';
    const usePullback = strategyType === 'pullback';
    let strategyFactory = null;

    if (!usePlaybook && !usePullback) {
        // Pine Script mode
        const parseResult = self.parsePineToJS(pineCode);
        if (parseResult.error) {
            self.postMessage({ type: 'error', error: 'Pine Script Fehler: ' + parseResult.error });
            return;
        }

        try {
            strategyFactory = new Function(
                'bars', 'computeSMA', 'computeEMA', 'computeRSI',
                'computeHighest', 'computeLowest', 'computeStdDev',
                'computeBB', 'computeMACD', 'computeStoch',
                'return ' + parseResult.code + '(bars, computeSMA, computeEMA, computeRSI, computeHighest, computeLowest, computeStdDev, computeBB, computeMACD, computeStoch);'
            );
        } catch (err) {
            self.postMessage({
                type: 'error',
                error: 'Generierter Code fehlerhaft: ' + err.message,
                generatedCode: parseResult.code
            });
            return;
        }
    }

    // 3. Run backtest on each pair
    const allTrades = [];
    const errors = [];

    for (let idx = 0; idx < pairs.length; idx++) {
        const pairName = pairs[idx];

        self.postMessage({
            type: 'progress',
            pair: pairName,
            index: idx,
            total: pairs.length
        });

        try {
            const bars = await self.loadPair(pairName, dataBaseUrl);

            let strategy;
            if (usePlaybook) {
                // Playbook v5 — create fresh instance per pair (zones are pair-specific)
                strategy = new self.PlaybookV5Strategy(strategyParams || {});
                strategy.init(bars);
            } else if (usePullback) {
                // Pullback-in-trend — fresh instance per pair (indicator arrays are pair-specific)
                strategy = new self.PullbackStrategy(strategyParams || {});
                strategy.init(bars);
            } else {
                // Pine Script — factory creates strategy object
                strategy = strategyFactory(
                    bars,
                    self.computeSMA, self.computeEMA, self.computeRSI,
                    self.computeHighest, self.computeLowest, self.computeStdDev,
                    self.computeBB, self.computeMACD, self.computeStoch
                );
            }

            const engine = new self.BacktestEngine(cfg, initialCapital, riskDecimal);
            engine.run(pairName, bars, strategy);
            const trades = engine.getTradeList();
            allTrades.push(...trades);
        } catch (err) {
            errors.push(pairName + ': ' + (err.message || String(err)));
        }
    }

    // 4. Compute analytics
    const metrics = self.computeMetrics(allTrades, initialCapital, riskDecimal);
    metrics.errors = errors;

    // 5. Send result
    self.postMessage({ type: 'result', data: metrics });
}
