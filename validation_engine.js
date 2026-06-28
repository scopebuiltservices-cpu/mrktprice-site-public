/* validation_engine.js — overfit promotion gate, 1:1 port of tools/market_map/validation_engine.py.
   purgedKfold (embargoed CV splits) + pboCscv (Probability of Backtest Overfitting, CSCV) + promotionGate
   (DSR + PBO). Locked to tools/validation_golden.json by tools/test_validation_parity.mjs. window.MrktValid. */
(function (root) {
  'use strict';
  function purgedKfold(n, k, embargo) {
    embargo = (embargo == null ? 0 : embargo);
    if (k < 2 || n < k) return [];
    var fold = Math.floor(n / k), out = [];
    for (var i = 0; i < k; i++) {
      var lo = i * fold, hi = (i === k - 1) ? n : (i + 1) * fold;
      var test = []; for (var t = lo; t < hi; t++) test.push(t);
      var elo = Math.max(0, lo - embargo), ehi = Math.min(n, hi + embargo);
      var train = []; for (var j = 0; j < n; j++) if (j < elo || j >= ehi) train.push(j);
      out.push([train, test]);
    }
    return out;
  }
  function _mean(xs) { return xs.length ? xs.reduce(function (p, x) { return p + x; }, 0) / xs.length : 0; }
  function _combos(arr, half) {
    var res = [];
    (function rec(start, cur) {
      if (cur.length === half) { res.push(cur.slice()); return; }
      for (var i = start; i < arr.length; i++) { cur.push(arr[i]); rec(i + 1, cur); cur.pop(); }
    })(0, []);
    return res;
  }
  function pboCscv(M, S) {
    S = (S == null ? 8 : S);
    var T = M.length, N = T ? M[0].length : 0;
    if (S % 2 || T < S || N < 2) return null;
    var blk = Math.floor(T / S), blocks = [];
    for (var b = 0; b < S; b++) { var rows = []; var end = (b === S - 1) ? T : (b + 1) * blk; for (var r = b * blk; r < end; r++) rows.push(r); blocks.push(rows); }
    var half = S / 2, idx = []; for (var s = 0; s < S; s++) idx.push(s);
    var combos = _combos(idx, half), nBelow = 0, tot = 0;
    combos.forEach(function (combo) {
      var isset = {}; combo.forEach(function (b2) { isset[b2] = 1; });
      var isRows = [], oosRows = [];
      for (var b2 = 0; b2 < S; b2++) (isset[b2] ? isRows : oosRows).push.apply(isset[b2] ? isRows : oosRows, blocks[b2]);
      var isP = [], oosP = [];
      for (var c = 0; c < N; c++) { isP.push(_mean(isRows.map(function (r) { return M[r][c]; }))); oosP.push(_mean(oosRows.map(function (r) { return M[r][c]; }))); }
      var nstar = 0; for (c = 1; c < N; c++) if (isP[c] > isP[nstar]) nstar = c;
      var order = idxN(N).sort(function (a, b) { return oosP[a] - oosP[b]; });
      var rank = order.indexOf(nstar) + 1, omega = rank / (N + 1);
      var lam = Math.log(omega / (1 - omega));
      if (lam < 0) nBelow++; tot++;
    });
    return tot ? nBelow / tot : null;
  }
  function idxN(N) { var a = []; for (var i = 0; i < N; i++) a.push(i); return a; }
  function promotionGate(dsr, pbo, minDsr, maxPbo) {
    minDsr = (minDsr == null ? 0.95 : minDsr); maxPbo = (maxPbo == null ? 0.5 : maxPbo);
    var okd = (dsr != null && dsr >= minDsr), okp = (pbo != null && pbo <= maxPbo), reasons = [];
    if (!okd) reasons.push('DSR ' + (dsr != null ? dsr.toFixed(3) : 'NaN') + ' < ' + minDsr.toFixed(2) + ' (selection-adjusted Sharpe not significant)');
    if (!okp) reasons.push('PBO ' + (pbo != null ? pbo.toFixed(2) : 'NaN') + ' > ' + maxPbo.toFixed(2) + ' (high backtest-overfit probability)');
    return { deployable: !!(okd && okp), dsr: dsr, pbo: pbo, reasons: reasons.length ? reasons : ['passes DSR + PBO'] };
  }
  var API = { purgedKfold: purgedKfold, pboCscv: pboCscv, promotionGate: promotionGate };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktValid = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
