// pine-parser.js — Pine Script to JavaScript Strategy Converter
// Usage: importScripts('pine-parser.js') in a Web Worker
// Converts common Pine Script v5/v6 constructs to a JS strategy function.
//
// Supported indicators:
//   ta.sma(), ta.ema(), ta.rsi(), ta.atr()
//   ta.highest(), ta.lowest(), ta.stdev()
//   ta.bb() (Bollinger Bands), ta.macd(), ta.stoch()
//   ta.crossover(), ta.crossunder()
//
// Supported strategy functions:
//   strategy.entry(), strategy.close(), strategy.close_all()
//   strategy.exit() with stop/limit
//   input() / input.int() / input.float() with defaults
//
// Supported math:
//   math.abs(), math.max(), math.min(), math.sqrt(), math.log()
//   nz() for null-safe access

(function (ctx) {
  'use strict';

  // =========================================================================
  // Pine Script Templates
  // =========================================================================

  var PINE_TEMPLATES = {
    'SMA Cross': [
      '//@version=5',
      'strategy("SMA Cross", overlay=true)',
      '',
      'fastLen = input.int(20, "Fast Length")',
      'slowLen = input.int(50, "Slow Length")',
      '',
      'fastMA = ta.sma(close, fastLen)',
      'slowMA = ta.sma(close, slowLen)',
      '',
      'longCondition = ta.crossover(fastMA, slowMA)',
      'shortCondition = ta.crossunder(fastMA, slowMA)',
      '',
      'if longCondition',
      '    strategy.entry("Long", strategy.long)',
      '',
      'if shortCondition',
      '    strategy.entry("Short", strategy.short)'
    ].join('\n'),

    'RSI Mean Reversion': [
      '//@version=5',
      'strategy("RSI Mean Reversion", overlay=true)',
      '',
      'rsiLen = input.int(14, "RSI Length")',
      'rsiOB = input.int(70, "Overbought")',
      'rsiOS = input.int(30, "Oversold")',
      '',
      'rsiVal = ta.rsi(close, rsiLen)',
      '',
      'if rsiVal < rsiOS',
      '    strategy.entry("Long", strategy.long)',
      '',
      'if rsiVal > rsiOB',
      '    strategy.entry("Short", strategy.short)'
    ].join('\n'),

    'MACD Crossover': [
      '//@version=5',
      'strategy("MACD Crossover", overlay=false)',
      '',
      'fastLen = input.int(12, "Fast Length")',
      'slowLen = input.int(26, "Slow Length")',
      'sigLen  = input.int(9, "Signal Length")',
      '',
      '[macdLine, signalLine, hist] = ta.macd(close, fastLen, slowLen, sigLen)',
      '',
      'if ta.crossover(macdLine, signalLine)',
      '    strategy.entry("Long", strategy.long)',
      '',
      'if ta.crossunder(macdLine, signalLine)',
      '    strategy.entry("Short", strategy.short)'
    ].join('\n'),

    'Bollinger Band Bounce': [
      '//@version=5',
      'strategy("Bollinger Band Bounce", overlay=true)',
      '',
      'bbLen  = input.int(20, "BB Length")',
      'bbMult = input.float(2.0, "BB Multiplier")',
      '',
      '[middle, upper, lower] = ta.bb(close, bbLen, bbMult)',
      '',
      'if close < lower',
      '    strategy.entry("Long", strategy.long)',
      '',
      'if close > upper',
      '    strategy.entry("Short", strategy.short)'
    ].join('\n'),

    'EMA Cross': [
      '//@version=5',
      'strategy("EMA Cross", overlay=true)',
      '',
      'fastLen = input.int(12, "Fast Length")',
      'slowLen = input.int(26, "Slow Length")',
      '',
      'fastEMA = ta.ema(close, fastLen)',
      'slowEMA = ta.ema(close, slowLen)',
      '',
      'if ta.crossover(fastEMA, slowEMA)',
      '    strategy.entry("Long", strategy.long)',
      '',
      'if ta.crossunder(fastEMA, slowEMA)',
      '    strategy.entry("Short", strategy.short)'
    ].join('\n'),

    'Stochastic + RSI': [
      '//@version=5',
      'strategy("Stochastic + RSI", overlay=true)',
      '',
      'stochLen = input.int(14, "Stoch Length")',
      'rsiLen   = input.int(14, "RSI Length")',
      '',
      'stochVal = ta.stoch(close, high, low, stochLen)',
      'rsiVal   = ta.rsi(close, rsiLen)',
      '',
      'if stochVal < 20 and rsiVal < 30',
      '    strategy.entry("Long", strategy.long)',
      '',
      'if stochVal > 80 and rsiVal > 70',
      '    strategy.entry("Short", strategy.short)'
    ].join('\n')
  };

  // =========================================================================
  // Internal helpers
  // =========================================================================

  /**
   * Resolve a value that might be an input variable name to its numeric value.
   */
  function _resolveInput(val, inputVars) {
    if (inputVars.hasOwnProperty(val)) {
      return inputVars[val];
    }
    // Already a number literal?
    if (/^-?\d+(\.\d+)?$/.test(val)) {
      return val;
    }
    return val;
  }

  /**
   * Resolve a Pine variable name to a JS expression for use inside generateSignal.
   * Returns a string like "sma_20[i]" or "bar.c".
   */
  function _resolveVar(varName, variables, indicators) {
    var direct = {
      'close': 'bar.c', 'open': 'bar.o', 'high': 'bar.h', 'low': 'bar.l',
      'volume': '0', 'bar_index': 'i', 'true': 'true', 'false': 'false',
      'na': 'null'
    };

    if (direct.hasOwnProperty(varName)) {
      return direct[varName];
    }

    // Check if it's a known indicator variable
    for (var k = 0; k < indicators.length; k++) {
      var ind = indicators[k];
      if (ind[1] === varName) {
        var kind = ind[0];
        if (kind === 'sma')     return 'sma_' + ind[3] + '[i]';
        if (kind === 'ema')     return 'ema_' + ind[3] + '[i]';
        if (kind === 'rsi')     return 'rsi_' + ind[3] + '[i]';
        if (kind === 'atr')     return 'bar.atr';
        if (kind === 'highest') return 'highest_' + ind[3] + '[i]';
        if (kind === 'lowest')  return 'lowest_' + ind[3] + '[i]';
        if (kind === 'stdev')   return 'stdev_' + ind[3] + '[i]';
        if (kind === 'stoch')   return 'stoch_' + ind[3] + '[i]';
        if (kind === 'crossover' || kind === 'crossunder') {
          return kind + '_' + ind[2] + '_' + ind[3] + '(i)';
        }
      }
    }

    // Check named sub-variables (BB middle/upper/lower, MACD line/signal/hist)
    if (variables.hasOwnProperty(varName)) {
      var v = variables[varName];
      if (/^bb_/.test(v) && /_middle$/.test(v))  return v + '[i]';
      if (/^bb_/.test(v) && /_upper$/.test(v))   return v + '[i]';
      if (/^bb_/.test(v) && /_lower$/.test(v))   return v + '[i]';
      if (/^macd_/.test(v) && /_line$/.test(v))   return v + '[i]';
      if (/^macd_/.test(v) && /_signal$/.test(v)) return v + '[i]';
      if (/^macd_/.test(v) && /_hist$/.test(v))   return v + '[i]';
      // Check if it resolves to another indicator
      for (var j = 0; j < indicators.length; j++) {
        if (indicators[j][1] === v) {
          return _resolveVar(v, {}, indicators);
        }
      }
    }

    // Try to parse as number
    if (/^-?\d+(\.\d+)?$/.test(varName)) {
      return varName;
    }

    return '0 /* unresolved: ' + varName + ' */';
  }

  /**
   * Translate a Pine condition string to JavaScript.
   */
  function _translateCondition(cond, variables, indicators) {
    // Replace Pine logical operators with JS equivalents
    cond = cond.replace(/\band\b/g, '&&');
    cond = cond.replace(/\bor\b/g, '||');
    cond = cond.replace(/\bnot\b/g, '!');

    // Replace math functions
    cond = cond.replace(/math\.abs\(/g, 'Math.abs(');
    cond = cond.replace(/math\.max\(/g, 'Math.max(');
    cond = cond.replace(/math\.min\(/g, 'Math.min(');
    cond = cond.replace(/math\.sqrt\(/g, 'Math.sqrt(');
    cond = cond.replace(/math\.log\(/g, 'Math.log(');

    // Replace nz()
    cond = cond.replace(/nz\((\w+)(?:,\s*(\w+))?\)/g, function (match, a, b) {
      var resolved = _resolveVar(a, variables, indicators);
      var fallback = b || '0';
      return '(' + resolved + ' != null ? ' + resolved + ' : ' + fallback + ')';
    });

    // Replace inline ta.crossover/crossunder
    cond = cond.replace(/ta\.crossover\(\s*(\w+)\s*,\s*(\w+)\s*\)/g, function (match, a, b) {
      return 'crossover_' + a + '_' + b + '(i)';
    });
    cond = cond.replace(/ta\.crossunder\(\s*(\w+)\s*,\s*(\w+)\s*\)/g, function (match, a, b) {
      return 'crossunder_' + a + '_' + b + '(i)';
    });

    // If the whole condition is already a crossover/crossunder call, return it
    if (/^cross(?:over|under)_\w+_\w+\(i\)$/.test(cond)) {
      return cond;
    }

    // Collect tokens and build replacements
    var tokens = cond.match(/\b\w+\b/g) || [];
    var replacements = {};
    var skip = {
      '&&': 1, '||': 1, '!': 1, 'true': 1, 'false': 1, 'null': 1,
      'Math': 1, 'abs': 1, 'max': 1, 'min': 1, 'sqrt': 1, 'log': 1,
      'i': 1, 'bar': 1, 'crossover': 1, 'crossunder': 1
    };

    for (var t = 0; t < tokens.length; t++) {
      var token = tokens[t];
      if (skip[token]) continue;
      // Skip if token is part of a crossover/crossunder function name
      if (/^crossover_|^crossunder_/.test(token)) continue;
      var resolved = _resolveVar(token, variables, indicators);
      if (resolved !== token) {
        replacements[token] = resolved;
      }
    }

    // Apply replacements (longest first to avoid partial matches)
    var keys = Object.keys(replacements).sort(function (a, b) { return b.length - a.length; });
    for (var r = 0; r < keys.length; r++) {
      var old = keys[r];
      var rep = replacements[old];
      cond = cond.replace(new RegExp('\\b' + old.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'g'), rep);
    }

    return cond;
  }

  // =========================================================================
  // Main parser
  // =========================================================================

  /**
   * Parse Pine Script code and return a JS strategy function body string.
   * @param {string} pineCode - The Pine Script source code.
   * @returns {{ code: string|null, error: string|null }}
   */
  function parsePineToJS(pineCode) {
    try {
      var indicators = [];
      var variables = {};
      var inputVars = {};
      var slExpr = null;
      var tpExpr = null;

      var lines = pineCode.trim().split('\n');

      // -------------------------------------------------------------------
      // First pass: collect variable assignments and indicators
      // -------------------------------------------------------------------
      for (var li = 0; li < lines.length; li++) {
        var line = lines[li].trim();
        if (!line || line.charAt(0) === '/' && line.charAt(1) === '/') continue;

        // Skip decorators and non-code lines
        var skipPrefixes = [
          'strategy(', 'plot(', 'bgcolor(', 'plotshape(', 'alertcondition(',
          '//@', 'indicator(', 'hline(', 'fill(', 'barcolor(', 'plotchar(',
          'label.', 'line.', 'box.', 'table.'
        ];
        var skipLine = false;
        for (var sp = 0; sp < skipPrefixes.length; sp++) {
          if (line.indexOf(skipPrefixes[sp]) === 0) { skipLine = true; break; }
        }
        if (skipLine) continue;

        // ---- Destructured BB: [middle, upper, lower] = ta.bb(...) ----
        var m2 = line.match(/^\[(\w+),\s*(\w+),\s*(\w+)\]\s*=\s*ta\.bb\(\s*(\w+)\s*,\s*(\w+)\s*,\s*([\w.]+)\s*\)/);
        if (m2) {
          var midName = m2[1], upName = m2[2], lowName = m2[3];
          var bbSrc = m2[4], bbLen = m2[5], bbMult = m2[6];
          var bbLenVal = _resolveInput(bbLen, inputVars);
          var bbMultVal = _resolveInput(bbMult, inputVars);
          var bbId = 'bb_' + bbLenVal;
          indicators.push(['bb', bbId, bbSrc, bbLenVal, bbMultVal]);
          variables[midName] = bbId + '_middle';
          variables[upName]  = bbId + '_upper';
          variables[lowName] = bbId + '_lower';
          continue;
        }

        // ---- Destructured MACD: [line, signal, hist] = ta.macd(...) ----
        var m3 = line.match(/^\[(\w+),\s*(\w+),\s*(\w+)\]\s*=\s*ta\.macd\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)/);
        if (m3) {
          var ml = m3[1], sl = m3[2], hl = m3[3];
          var macdSrc = m3[4];
          var macdFast = _resolveInput(m3[5], inputVars);
          var macdSlow = _resolveInput(m3[6], inputVars);
          var macdSig  = _resolveInput(m3[7], inputVars);
          var macdId = 'macd_' + macdFast + '_' + macdSlow;
          indicators.push(['macd', macdId, macdSrc, macdFast, macdSlow, macdSig]);
          variables[ml] = macdId + '_line';
          variables[sl] = macdId + '_signal';
          variables[hl] = macdId + '_hist';
          continue;
        }

        // ---- Parse variable assignments: varName = expression ----
        var assign = line.match(/^(?:var\s+)?(\w+)\s*=\s*(.+)$/);
        if (!assign) continue;

        var varName = assign[1];
        var expr = assign[2].trim();

        // ta.sma(source, length)
        var m = expr.match(/^ta\.sma\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[2], inputVars);
          indicators.push(['sma', varName, m[1], lenVal]);
          variables[varName] = 'sma_' + lenVal;
          continue;
        }

        // ta.ema(source, length)
        m = expr.match(/^ta\.ema\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[2], inputVars);
          indicators.push(['ema', varName, m[1], lenVal]);
          variables[varName] = 'ema_' + lenVal;
          continue;
        }

        // ta.rsi(source, length)
        m = expr.match(/^ta\.rsi\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[2], inputVars);
          indicators.push(['rsi', varName, m[1], lenVal]);
          variables[varName] = 'rsi_' + lenVal;
          continue;
        }

        // ta.atr(length)
        m = expr.match(/^ta\.atr\(\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[1], inputVars);
          indicators.push(['atr', varName, 'close', lenVal]);
          variables[varName] = 'atr';
          continue;
        }

        // ta.highest(source, length)
        m = expr.match(/^ta\.highest\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[2], inputVars);
          indicators.push(['highest', varName, m[1], lenVal]);
          variables[varName] = 'highest_' + lenVal;
          continue;
        }

        // ta.lowest(source, length)
        m = expr.match(/^ta\.lowest\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[2], inputVars);
          indicators.push(['lowest', varName, m[1], lenVal]);
          variables[varName] = 'lowest_' + lenVal;
          continue;
        }

        // ta.stdev(source, length)
        m = expr.match(/^ta\.stdev\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[2], inputVars);
          indicators.push(['stdev', varName, m[1], lenVal]);
          variables[varName] = 'stdev_' + lenVal;
          continue;
        }

        // ta.bb(source, length, mult) — single variable (non-destructured)
        m = expr.match(/^ta\.bb\(\s*(\w+)\s*,\s*(\w+)\s*,\s*([\w.]+)\s*\)$/);
        if (m) {
          var bbLenVal = _resolveInput(m[2], inputVars);
          var bbMultVal = _resolveInput(m[3], inputVars);
          indicators.push(['bb', varName, m[1], bbLenVal, bbMultVal]);
          variables[varName] = 'bb_' + bbLenVal;
          variables[varName + '_middle'] = 'bb_' + bbLenVal + '_middle';
          variables[varName + '_upper']  = 'bb_' + bbLenVal + '_upper';
          variables[varName + '_lower']  = 'bb_' + bbLenVal + '_lower';
          continue;
        }

        // ta.macd(source, fast, slow, signal) — single variable (non-destructured)
        m = expr.match(/^ta\.macd\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var fastVal = _resolveInput(m[2], inputVars);
          var slowVal = _resolveInput(m[3], inputVars);
          var sigVal  = _resolveInput(m[4], inputVars);
          indicators.push(['macd', varName, m[1], fastVal, slowVal, sigVal]);
          variables[varName] = 'macd_' + fastVal + '_' + slowVal;
          continue;
        }

        // ta.stoch(close, high, low, length)
        m = expr.match(/^ta\.stoch\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var lenVal = _resolveInput(m[4], inputVars);
          indicators.push(['stoch', varName, 'close', lenVal]);
          variables[varName] = 'stoch_' + lenVal;
          continue;
        }

        // ta.crossover(a, b)
        m = expr.match(/^ta\.crossover\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var a = m[1], b = m[2];
          variables[varName] = 'crossover_' + a + '_' + b;
          indicators.push(['crossover', varName, a, b]);
          continue;
        }

        // ta.crossunder(a, b)
        m = expr.match(/^ta\.crossunder\(\s*(\w+)\s*,\s*(\w+)\s*\)$/);
        if (m) {
          var a = m[1], b = m[2];
          variables[varName] = 'crossunder_' + a + '_' + b;
          indicators.push(['crossunder', varName, a, b]);
          continue;
        }

        // input() / input.int() / input.float() — extract default
        m = expr.match(/^input(?:\.\w+)?\(\s*(?:defval\s*=\s*)?([^,)]+)/);
        if (m) {
          var val = m[1].trim().replace(/^["']|["']$/g, '');
          // Try to parse as number
          if (/^-?\d+$/.test(val)) {
            // integer — keep as is
          } else if (/^-?\d+\.\d+$/.test(val)) {
            // float — keep as is
          } else {
            val = '0';
          }
          inputVars[varName] = val;
          variables[varName] = val;
          continue;
        }

        // Simple expression assignment
        variables[varName] = expr;
      }

      // -------------------------------------------------------------------
      // Helper: ensure crossover/crossunder helpers from inline conditions
      // -------------------------------------------------------------------
      function _ensureCrossoverHelper(condText) {
        var re1 = /ta\.crossover\(\s*(\w+)\s*,\s*(\w+)\s*\)/g;
        var mc;
        while ((mc = re1.exec(condText)) !== null) {
          var a = mc[1], b = mc[2];
          var exists = false;
          for (var q = 0; q < indicators.length; q++) {
            if (indicators[q][0] === 'crossover' && indicators[q][2] === a && indicators[q][3] === b) {
              exists = true; break;
            }
          }
          if (!exists) {
            indicators.push(['crossover', 'crossover_' + a + '_' + b, a, b]);
          }
        }
        var re2 = /ta\.crossunder\(\s*(\w+)\s*,\s*(\w+)\s*\)/g;
        while ((mc = re2.exec(condText)) !== null) {
          var a = mc[1], b = mc[2];
          var exists = false;
          for (var q = 0; q < indicators.length; q++) {
            if (indicators[q][0] === 'crossunder' && indicators[q][2] === a && indicators[q][3] === b) {
              exists = true; break;
            }
          }
          if (!exists) {
            indicators.push(['crossunder', 'crossunder_' + a + '_' + b, a, b]);
          }
        }
      }

      // -------------------------------------------------------------------
      // Second pass: find long/short conditions and entry/exit patterns
      // -------------------------------------------------------------------
      var longConds = [];
      var shortConds = [];
      var closeConds = [];
      var i = 0;

      while (i < lines.length) {
        var line = lines[i].trim();
        i++;

        if (!line || (line.charAt(0) === '/' && line.charAt(1) === '/')) continue;

        // Match if statement — Pine uses `if condition` (no wrapping parens required)
        // CRITICAL: use `if\s+(.+?)\s*$` — do NOT strip closing parens with the regex
        var mIf = line.match(/^if\s+(.+?)\s*$/);
        if (mIf) {
          var currentCondition = mIf[1].trim();

          // Strip wrapping parens only if they are balanced outer parens
          if (currentCondition.charAt(0) === '(' && currentCondition.charAt(currentCondition.length - 1) === ')') {
            var inner = currentCondition.substring(1, currentCondition.length - 1);
            var depth = 0;
            var balanced = true;
            for (var ci = 0; ci < inner.length; ci++) {
              if (inner.charAt(ci) === '(') depth++;
              else if (inner.charAt(ci) === ')') depth--;
              if (depth < 0) { balanced = false; break; }
            }
            if (balanced && depth === 0) {
              currentCondition = inner.trim();
            }
          }

          _ensureCrossoverHelper(currentCondition);

          // Check subsequent lines for strategy calls
          while (i < lines.length) {
            var nextLine = lines[i];
            var nextTrimmed = nextLine.trim();
            if (!nextTrimmed || (nextTrimmed.charAt(0) === '/' && nextTrimmed.charAt(1) === '/')) {
              i++;
              continue;
            }
            // Must be indented or start with strategy.
            if (nextLine.charAt(0) === ' ' || nextLine.charAt(0) === '\t' || nextTrimmed.indexOf('strategy.') === 0) {
              if (nextTrimmed.indexOf('strategy.entry') !== -1) {
                if (nextTrimmed.indexOf('strategy.long') !== -1 ||
                    nextTrimmed.indexOf('"Long"') !== -1 ||
                    nextTrimmed.indexOf("'Long'") !== -1) {
                  longConds.push(currentCondition);
                } else if (nextTrimmed.indexOf('strategy.short') !== -1 ||
                           nextTrimmed.indexOf('"Short"') !== -1 ||
                           nextTrimmed.indexOf("'Short'") !== -1) {
                  shortConds.push(currentCondition);
                }
              } else if (nextTrimmed.indexOf('strategy.close') !== -1) {
                closeConds.push(currentCondition);
              }

              // Check for strategy.exit with stop/limit
              var mExit = nextTrimmed.match(/strategy\.exit\(.+?stop\s*=\s*(.+?)(?:,|\))/);
              if (mExit) {
                slExpr = mExit[1].trim();
              }
              var mTp = nextTrimmed.match(/strategy\.exit\(.+?limit\s*=\s*(.+?)(?:,|\))/);
              if (mTp) {
                tpExpr = mTp[1].trim();
              }

              i++;
            } else {
              break;
            }
          }
          continue;
        }

        // Inline ternary strategy calls
        if (line.indexOf('strategy.entry') !== -1 && line.indexOf('?') !== -1) {
          var mTern = line.match(/(.+?)\s*\?\s*strategy\.entry/);
          if (mTern) {
            var cond = mTern[1].trim();
            if (line.indexOf('strategy.long') !== -1 || line.indexOf('"Long"') !== -1) {
              longConds.push(cond);
            } else if (line.indexOf('strategy.short') !== -1 || line.indexOf('"Short"') !== -1) {
              shortConds.push(cond);
            }
          }
        }
      }

      // -------------------------------------------------------------------
      // Build JS strategy code
      // -------------------------------------------------------------------
      var codeLines = [];

      // Function wrapper opening
      codeLines.push('(function(bars, computeSMA, computeEMA, computeRSI, computeHighest, computeLowest, computeStdDev, computeBB, computeMACD, computeStoch) {');

      // Track which indicator arrays we've already emitted to avoid duplicates
      var emitted = {};

      // Pre-compute indicators
      for (var k = 0; k < indicators.length; k++) {
        var ind = indicators[k];
        var kind = ind[0];

        if (kind === 'sma') {
          var key = 'sma_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeSMA(bars, ' + ind[3] + ');');
            emitted[key] = true;
          }
        } else if (kind === 'ema') {
          var key = 'ema_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeEMA(bars, ' + ind[3] + ');');
            emitted[key] = true;
          }
        } else if (kind === 'rsi') {
          var key = 'rsi_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeRSI(bars, ' + ind[3] + ');');
            emitted[key] = true;
          }
        } else if (kind === 'atr') {
          codeLines.push('    // ATR uses bar.atr from engine');
        } else if (kind === 'highest') {
          var src = ind[2];
          var key = 'highest_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeHighest(bars, ' + ind[3] + ', "' + src + '");');
            emitted[key] = true;
          }
        } else if (kind === 'lowest') {
          var src = ind[2];
          var key = 'lowest_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeLowest(bars, ' + ind[3] + ', "' + src + '");');
            emitted[key] = true;
          }
        } else if (kind === 'stdev') {
          var key = 'stdev_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeStdDev(bars, ' + ind[3] + ');');
            emitted[key] = true;
          }
        } else if (kind === 'bb') {
          var bbVar = ind[1]; // e.g. "bb_20"
          if (!emitted[bbVar]) {
            codeLines.push('    var _' + bbVar + ' = computeBB(bars, ' + ind[3] + ', ' + ind[4] + ');');
            codeLines.push('    var ' + bbVar + '_middle = _' + bbVar + '.middle;');
            codeLines.push('    var ' + bbVar + '_upper = _' + bbVar + '.upper;');
            codeLines.push('    var ' + bbVar + '_lower = _' + bbVar + '.lower;');
            emitted[bbVar] = true;
          }
        } else if (kind === 'macd') {
          var macdVar = ind[1]; // e.g. "macd_12_26"
          if (!emitted[macdVar]) {
            codeLines.push('    var _' + macdVar + ' = computeMACD(bars, ' + ind[3] + ', ' + ind[4] + ', ' + ind[5] + ');');
            codeLines.push('    var ' + macdVar + '_line = _' + macdVar + '.line;');
            codeLines.push('    var ' + macdVar + '_signal = _' + macdVar + '.signal;');
            codeLines.push('    var ' + macdVar + '_hist = _' + macdVar + '.hist;');
            emitted[macdVar] = true;
          }
        } else if (kind === 'stoch') {
          var key = 'stoch_' + ind[3];
          if (!emitted[key]) {
            codeLines.push('    var ' + key + ' = computeStoch(bars, ' + ind[3] + ');');
            emitted[key] = true;
          }
        }
        // crossover/crossunder are handled below as helper functions
      }

      codeLines.push('');

      // Build crossover/crossunder helper functions
      for (var k = 0; k < indicators.length; k++) {
        var ind = indicators[k];
        if (ind[0] === 'crossover') {
          var a = ind[2], b = ind[3];
          var aRes = _resolveVar(a, variables, indicators).replace(/\[i\]/g, '[idx]');
          var bRes = _resolveVar(b, variables, indicators).replace(/\[i\]/g, '[idx]');
          var aPrev = aRes.replace(/\[idx\]/g, '[idx-1]');
          var bPrev = bRes.replace(/\[idx\]/g, '[idx-1]');
          var fnName = 'crossover_' + a + '_' + b;
          if (!emitted[fnName]) {
            codeLines.push('    function ' + fnName + '(idx) {');
            codeLines.push('        if (idx < 1) return false;');
            codeLines.push('        return ' + aRes + ' > ' + bRes + ' && ' + aPrev + ' <= ' + bPrev + ';');
            codeLines.push('    }');
            emitted[fnName] = true;
          }
        } else if (ind[0] === 'crossunder') {
          var a = ind[2], b = ind[3];
          var aRes = _resolveVar(a, variables, indicators).replace(/\[i\]/g, '[idx]');
          var bRes = _resolveVar(b, variables, indicators).replace(/\[i\]/g, '[idx]');
          var aPrev = aRes.replace(/\[idx\]/g, '[idx-1]');
          var bPrev = bRes.replace(/\[idx\]/g, '[idx-1]');
          var fnName = 'crossunder_' + a + '_' + b;
          if (!emitted[fnName]) {
            codeLines.push('    function ' + fnName + '(idx) {');
            codeLines.push('        if (idx < 1) return false;');
            codeLines.push('        return ' + aRes + ' < ' + bRes + ' && ' + aPrev + ' >= ' + bPrev + ';');
            codeLines.push('    }');
            emitted[fnName] = true;
          }
        }
      }

      codeLines.push('');

      // Build long/short signal expressions
      var longJS = 'false';
      if (longConds.length > 0) {
        var parts = [];
        for (var lc = 0; lc < longConds.length; lc++) {
          parts.push('(' + _translateCondition(longConds[lc], variables, indicators) + ')');
        }
        longJS = parts.join(' && ');
      }

      var shortJS = 'false';
      if (shortConds.length > 0) {
        var parts = [];
        for (var sc = 0; sc < shortConds.length; sc++) {
          parts.push('(' + _translateCondition(shortConds[sc], variables, indicators) + ')');
        }
        shortJS = parts.join(' && ');
      }

      // generateSignal function
      codeLines.push('    return {');
      codeLines.push('        generateSignal: function(i, bar, prev) {');
      codeLines.push('            if (i < 200 || bar.atr < 1e-10) return null;');
      codeLines.push('');
      codeLines.push('            var longSignal = ' + longJS + ';');
      codeLines.push('            var shortSignal = ' + shortJS + ';');
      codeLines.push('');
      codeLines.push('            if (longSignal) {');
      codeLines.push('                return { direction: 1, entry: bar.c, stopLoss: bar.c - 1.5 * bar.atr,');
      codeLines.push('                         zoneType: "pine_signal", patternType: "pine_long", features: {} };');
      codeLines.push('            }');
      codeLines.push('            if (shortSignal) {');
      codeLines.push('                return { direction: -1, entry: bar.c, stopLoss: bar.c + 1.5 * bar.atr,');
      codeLines.push('                         zoneType: "pine_signal", patternType: "pine_short", features: {} };');
      codeLines.push('            }');
      codeLines.push('            return null;');
      codeLines.push('        }');
      codeLines.push('    };');
      codeLines.push('})');

      return { code: codeLines.join('\n'), error: null };

    } catch (e) {
      return { code: null, error: 'Pine parse error: ' + (e.message || String(e)) };
    }
  }

  // =========================================================================
  // Expose on self / globalThis for Web Worker importScripts()
  // =========================================================================

  ctx.parsePineToJS = parsePineToJS;
  ctx.PINE_TEMPLATES = PINE_TEMPLATES;

})(self);
