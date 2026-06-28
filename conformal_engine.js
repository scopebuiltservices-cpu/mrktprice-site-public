/* conformal_engine.js — 1:1 JS port of conformal_engine.py. Conformalized Quantile Regression (CQR;
   Romano, Patterson & Candès 2019) + split-conformal helpers. Distribution-free finite-sample marginal
   coverage >= 1-alpha. Browser-facing so the cone/board can conformalize quantile predictions client-side.
   exports: window.MrktConformal (browser) / module.exports (node). Research only, not advice. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktConformal = m;
})(this, function () {
  'use strict';

  function pinballLoss(y, q, tau) { var d = y - q; return d >= 0 ? tau * d : (tau - 1.0) * d; }

  function gaussianQuantiles(mu, sd, alpha) {
    if (alpha == null) alpha = 0.10;
    var z = normPpf(1.0 - alpha / 2.0);
    return [mu - z * sd, mu + z * sd];
  }

  function cqrScores(calQlo, calQhi, calY) {
    var n = calY.length, E = new Array(n);
    for (var i = 0; i < n; i++) E[i] = Math.max(calQlo[i] - calY[i], calY[i] - calQhi[i]);
    return E;
  }

  function cqrPad(calQlo, calQhi, calY, alpha) {
    if (alpha == null) alpha = 0.10;
    var E = cqrScores(calQlo, calQhi, calY).slice().sort(function (a, b) { return a - b; });
    var n = E.length;
    if (n === 0) return Infinity;
    var k = Math.ceil((1.0 - alpha) * (n + 1));
    if (k > n) return Infinity;
    return E[k - 1];
  }

  function cqrInterval(qlo, qhi, pad) { return [qlo - pad, qhi + pad]; }

  function intervalCoverage(y, lo, hi) {
    var n = y.length; if (n === 0) return 0.0;
    var c = 0; for (var i = 0; i < n; i++) if (lo[i] <= y[i] && y[i] <= hi[i]) c++;
    return c / n;
  }

  function intervalScore(y, lo, hi, alpha) {
    if (alpha == null) alpha = 0.10;
    var n = y.length; if (n === 0) return 0.0;
    var s = 0.0;
    for (var i = 0; i < n; i++) {
      s += hi[i] - lo[i];
      if (y[i] < lo[i]) s += (2.0 / alpha) * (lo[i] - y[i]);
      else if (y[i] > hi[i]) s += (2.0 / alpha) * (y[i] - hi[i]);
    }
    return s / n;
  }

  function cqrCalibrateApply(calQlo, calQhi, calY, testQlo, testQhi, alpha) {
    if (alpha == null) alpha = 0.10;
    var pad = cqrPad(calQlo, calQhi, calY, alpha), n = testQlo.length;
    var lo = new Array(n), hi = new Array(n);
    for (var i = 0; i < n; i++) { lo[i] = testQlo[i] - pad; hi[i] = testQhi[i] + pad; }
    return { lo: lo, hi: hi, pad: pad };
  }

  function normPpf(p) {
    if (p <= 0.0) return -Infinity;
    if (p >= 1.0) return Infinity;
    var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
    var b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01];
    var c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
    var d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];
    var pl = 0.02425, q, r;
    if (p < pl) { q = Math.sqrt(-2.0 * Math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0); }
    if (p <= 1.0 - pl) { q = p - 0.5; r = q*q; return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0); }
    q = Math.sqrt(-2.0 * Math.log(1.0 - p));
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0);
  }

  return { pinballLoss: pinballLoss, gaussianQuantiles: gaussianQuantiles, cqrScores: cqrScores,
    cqrPad: cqrPad, cqrInterval: cqrInterval, intervalCoverage: intervalCoverage,
    intervalScore: intervalScore, cqrCalibrateApply: cqrCalibrateApply, normPpf: normPpf };
});
