/* projlearn_engine.js — 1:1 JS port of projlearn_engine.py. Mincer-Zarnowitz recalibration of the
   projClose-vs-priceNow forecast (learn from realized outcomes). exports window.MrktProjLearn. Research only. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktProjLearn = m;
})(this, function () {
  'use strict';
  function mean(x) { return x.length ? x.reduce(function (a, b) { return a + b; }, 0) / x.length : 0; }
  function mincerZarnowitz(pred, realized) {
    var n = pred.length;
    if (n < 3) return { alpha: 0, beta: 1, r2: 0, n: n };
    var mp = mean(pred), mr = mean(realized), spp = 0, spr = 0, i;
    for (i = 0; i < n; i++) { spp += (pred[i] - mp) * (pred[i] - mp); spr += (pred[i] - mp) * (realized[i] - mr); }
    var beta = spp > 0 ? spr / spp : 1, alpha = mr - beta * mp, sse = 0, sst = 0;
    for (i = 0; i < n; i++) { var e = realized[i] - (alpha + beta * pred[i]); sse += e * e; sst += (realized[i] - mr) * (realized[i] - mr); }
    return { alpha: alpha, beta: beta, r2: sst > 0 ? 1 - sse / sst : 0, n: n };
  }
  function recalibrate(pred, alpha, beta) { return alpha + beta * pred; }
  function skillVsNaive(pred, realized) {
    var n = pred.length; if (!n) return 0; var mm = 0, mn = 0, i;
    for (i = 0; i < n; i++) { var d = realized[i] - pred[i]; mm += d * d; mn += realized[i] * realized[i]; }
    mm /= n; mn /= n; return mn > 0 ? 1 - mm / mn : 0;
  }
  function theilU2(pred, realized) {
    var n = pred.length; if (!n) return 1; var num = 0, den = 0, i;
    for (i = 0; i < n; i++) { var d = realized[i] - pred[i]; num += d * d; den += realized[i] * realized[i]; }
    return den > 0 ? Math.sqrt(num / n) / Math.sqrt(den / n) : 1;
  }
  function bias(pred, realized) { var n = pred.length; if (!n) return 0; var s = 0, i; for (i = 0; i < n; i++) s += realized[i] - pred[i]; return s / n; }
  function mae(pred, realized) { var n = pred.length; if (!n) return 0; var s = 0, i; for (i = 0; i < n; i++) s += Math.abs(realized[i] - pred[i]); return s / n; }
  function coverage(realized, lo, hi) { var n = realized.length; if (!n) return null; var c = 0, i; for (i = 0; i < n; i++) if (lo[i] <= realized[i] && realized[i] <= hi[i]) c++; return c / n; }
  function r6(x) { return Math.round(x * 1e6) / 1e6; }
  function r4(x) { return Math.round(x * 1e4) / 1e4; }
  function learn(pred, realized, tau, nMin) {
    if (tau == null) tau = 12; if (nMin == null) nMin = 8;
    var mz = mincerZarnowitz(pred, realized), n = mz.n, w = (n + tau) > 0 ? n / (n + tau) : 0;
    return { alpha: r6(mz.alpha), beta: r4(mz.beta), r2: r4(mz.r2), skill: r4(skillVsNaive(pred, realized)),
      theilU2: r4(theilU2(pred, realized)), bias: r6(bias(pred, realized)), mae: r6(mae(pred, realized)),
      n: n, applied: n >= nMin, wAlpha: r6(w * mz.alpha), wBeta: r4(w * mz.beta + (1 - w) * 1), shrink: Math.round(w * 1e3) / 1e3 };
  }
  return { mincerZarnowitz: mincerZarnowitz, recalibrate: recalibrate, skillVsNaive: skillVsNaive,
    theilU2: theilU2, bias: bias, mae: mae, coverage: coverage, learn: learn };
});
