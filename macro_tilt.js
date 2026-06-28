/* macro_tilt.js — full macro contribution to a name's expected return, 1:1 port of
   tools/market_map/macro_tilt.py. Integrates the COMPLETE complex into the Bull/Bear rank: every
   commodity + DXY + VIX via partial (multivariate Lasso) betas, and the REAL-rate curve via
   level/slope/curvature duration betas. Locked to tools/macro_golden.json by tools/test_macro_parity.mjs.
   Exposes window.MrktMacro (UMD). Pure, no deps. */
(function (root) {
  'use strict';
  function macroTilt(betas, moves, exclude) {
    if (!betas || !moves) return 0.0;
    var ex = {}; (exclude || ['MKT']).forEach(function (k) { ex[k] = 1; });
    var s = 0.0;
    for (var k in betas) {
      if (!Object.prototype.hasOwnProperty.call(betas, k) || ex[k]) continue;
      var b = betas[k], m = moves[k];
      if (b == null || m == null || b !== b || m !== m) continue;
      s += b * m;
    }
    return s;
  }
  function rateRealTilt(rate, move) {
    if (!rate || !move) return 0.0;
    var s = 0.0, pairs = [['bL', 'dL'], ['bS', 'dS'], ['bC', 'dC']];
    for (var i = 0; i < pairs.length; i++) {
      var b = rate[pairs[i][0]], m = move[pairs[i][1]];
      if (b == null || m == null || b !== b || m !== m) continue;
      s += b * m;
    }
    return s;
  }
  function combinedTilt(betas, moves, rate, ratemove, w_real, use_real) {
    w_real = (w_real == null ? 1.0 : w_real);
    use_real = (use_real == null ? true : use_real);
    var haveReal = !!(rate && ratemove && use_real);
    if (haveReal) return macroTilt(betas, moves, ['MKT', 'RATE']) + w_real * rateRealTilt(rate, ratemove);
    return macroTilt(betas, moves, ['MKT']);
  }
  var API = { macroTilt: macroTilt, rateRealTilt: rateRealTilt, combinedTilt: combinedTilt };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktMacro = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
