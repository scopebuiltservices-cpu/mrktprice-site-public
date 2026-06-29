/* proj_engine.js — 1:1 JS port of proj_engine.py (Fibonacci multi-horizon projection + accuracy, PDF 2).
   exports window.MrktProj / module.exports. Research only, not advice. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktProj = m;
})(this, function () {
  'use strict';
  function cumulativeDecayMultiplier(H, tau) {
    if (tau == null || tau <= 0) return H;
    var phi = Math.pow(0.5, 1.0 / tau);
    if (Math.abs(1 - phi) < 1e-12) return H;
    return (1 - Math.pow(phi, H)) / (1 - phi);
  }
  function buildFallbackProjection(priceNow, projClose1d, sigmaDaily, H, halfLife, capDaily, capH) {
    if (halfLife == null) halfLife = 3.0; if (capDaily == null) capDaily = 1.5; if (capH == null) capH = 2.0;
    if (!(priceNow > 0 && projClose1d > 0)) return null;
    var edge1 = Math.log(projClose1d / priceNow), lim1 = capDaily * sigmaDaily;
    var edge1c = Math.max(-lim1, Math.min(lim1, edge1));
    var M = cumulativeDecayMultiplier(H, halfLife), sigmaH = sigmaDaily * Math.sqrt(H);
    var muRaw = M * edge1c, limH = capH * sigmaH, muH = Math.max(-limH, Math.min(limH, muRaw));
    return { H: H, muH: muH, sigmaH: sigmaH, projCloseFwdH: priceNow * Math.exp(muH),
      pctVsNow: (Math.exp(muH) - 1) * 100, zEdgeH: sigmaH > 0 ? muH / sigmaH : 0, M: M };
  }
  function expectedPathPrice(priceNowAtForecast, muH, elapsed, H, halfLife) {
    if (halfLife == null) halfLife = 3.0;
    var mH = cumulativeDecayMultiplier(H, halfLife), me = cumulativeDecayMultiplier(elapsed, halfLife);
    var w = mH > 0 ? me / mH : 0;
    return priceNowAtForecast * Math.exp(w * muH);
  }
  function scoreAccuracy(actual, stored, sigmaH) {
    var sle = Math.log(actual / stored), sz = sigmaH > 0 ? sle / sigmaH : 0;
    return { signedLogError: sle, signedZError: sz, absZError: Math.abs(sz) };
  }
  function skillVsNaive(forecasts, actuals, priceNowAtForecast) {
    var n = forecasts.length; if (!n) return 0;
    var mm = 0, mn = 0, i;
    for (i = 0; i < n; i++) { mm += Math.abs(actuals[i] - forecasts[i]); mn += Math.abs(actuals[i] - priceNowAtForecast[i]); }
    mm /= n; mn /= n; return mn > 0 ? 1 - mm / mn : 0;
  }
  function ncdf(x) { return 0.5 * (1 + erf(x / Math.SQRT2)); }
  function erf(x) { var t = 1 / (1 + 0.3275911 * Math.abs(x)); var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y; }
  function probAboveNow(muH, sigmaH) { return sigmaH > 0 ? ncdf(muH / sigmaH) : 0.5; }
  return { cumulativeDecayMultiplier: cumulativeDecayMultiplier, buildFallbackProjection: buildFallbackProjection,
    expectedPathPrice: expectedPathPrice, scoreAccuracy: scoreAccuracy, skillVsNaive: skillVsNaive, probAboveNow: probAboveNow };
});
