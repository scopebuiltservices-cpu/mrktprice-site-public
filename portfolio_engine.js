/* portfolio_engine.js — allocation engine, 1:1 port of tools/market_map/portfolio_engine.py.
   Single-factor mean-variance optimum (Sherman-Morrison, O(n)) + long-only box/budget projection +
   turnover-aware transition. Locked to tools/portfolio_golden.json by tools/test_portfolio_parity.mjs.
   Exposes window.MrktPort. Pure, no deps. */
(function (root) {
  'use strict';
  function factorCov(beta, sigmaM, sigmaIdio) {
    var n = beta.length, c = sigmaM * sigmaM, out = [];
    for (var i = 0; i < n; i++) { var row = []; for (var j = 0; j < n; j++) row.push(c * beta[i] * beta[j] + (i === j ? sigmaIdio[i] * sigmaIdio[i] : 0)); out.push(row); }
    return out;
  }
  function mvWeightsFactor(mu, beta, sigmaM, sigmaIdio, lam) {
    lam = (lam == null ? 1 : lam);
    var n = mu.length, c = sigmaM * sigmaM, Dinv = [], Dm = [], Db = [], i;
    for (i = 0; i < n; i++) { Dinv.push(1 / (sigmaIdio[i] * sigmaIdio[i])); Dm.push(Dinv[i] * mu[i]); Db.push(Dinv[i] * beta[i]); }
    var bDb = 0, bDm = 0; for (i = 0; i < n; i++) { bDb += beta[i] * Db[i]; bDm += beta[i] * Dm[i]; }
    var k = c * bDm / (1 + c * bDb), w = [];
    for (i = 0; i < n; i++) w.push((Dm[i] - k * Db[i]) / lam);
    return w;
  }
  function projectLongOnly(wRaw, wMax, budget, iters) {
    wMax = (wMax == null ? 0.1 : wMax); budget = (budget == null ? 1 : budget); iters = (iters == null ? 50 : iters);
    var n = wRaw.length, w = wRaw.map(function (x) { return Math.max(0, x); }), i;
    var s = w.reduce(function (p, x) { return p + x; }, 0);
    if (s <= 0) return new Array(n).fill(budget / n);
    w = w.map(function (x) { return budget * x / s; });
    for (var it = 0; it < iters; it++) {
      var over = []; for (i = 0; i < n; i++) if (w[i] > wMax) over.push(i);
      if (!over.length) break;
      var spill = 0; over.forEach(function (i2) { spill += w[i2] - wMax; w[i2] = wMax; });
      var free = []; for (i = 0; i < n; i++) if (w[i] < wMax - 1e-12) free.push(i);
      var fs = 0; free.forEach(function (i2) { fs += w[i2]; });
      if (fs <= 0 || !free.length) return w;
      free.forEach(function (i2) { w[i2] += spill * w[i2] / fs; });
    }
    return w;
  }
  function turnoverBlend(wOpt, wPrev, step) {
    step = (step == null ? 1 : step);
    if (wPrev == null) return wOpt.slice();
    return wOpt.map(function (x, i) { return wPrev[i] + step * (x - wPrev[i]); });
  }
  var API = { factorCov: factorCov, mvWeightsFactor: mvWeightsFactor, projectLongOnly: projectLongOnly, turnoverBlend: turnoverBlend };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktPort = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
