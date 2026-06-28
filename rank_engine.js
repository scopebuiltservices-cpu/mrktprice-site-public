/* rank_engine.js — confidence-adjusted Bull/Bear ranking math, 1:1 port of tools/market_map/rank_engine.py.
   Locked to tools/rank_golden.json by tools/test_rank_parity.mjs. Exposes window.MrktRank (UMD). */
(function (root) {
  'use strict';
  function grinoldKahn(ic, sigma, z) { return ic * sigma * z; }
  function alphaForecastSe(residSd, alpha, alphaMean, sxx, n) {
    // mean-response (estimation) SE of the alpha->return calibration prediction; leverage-aware.
    if (!(residSd > 0 && sxx > 0 && n >= 3)) return null;
    return residSd * Math.sqrt(1 / n + (alpha - alphaMean) * (alpha - alphaMean) / sxx);
  }
  function convictionSigma(base, z, floor, full) {
    floor = (floor == null ? 0.2 : floor); full = (full == null ? 1.5 : full);
    var rel = full > 0 ? Math.abs(z) / full : 0;
    rel = Math.max(floor, Math.min(1, rel));
    return base / rel;
  }
  function lcbScore(mu, sigma, k) {
    k = (k == null ? 0.5 : k);
    if (sigma == null || sigma !== sigma || sigma < 0) return mu;
    var pen = k * sigma;
    return mu >= 0 ? mu - pen : mu + pen;
  }
  function deflatedConviction(z, n) {
    if (n == null || n < 2) return z;
    var bar = Math.sqrt(2 * Math.log(n));
    var excess = Math.max(0, Math.abs(z) - bar);
    return z === 0 ? 0 : (z < 0 ? -excess : excess);
  }
  function steinShrink(x, se, tau, center) {
    center = (center == null ? 0 : center);
    if (se == null || se <= 0 || tau == null || tau <= 0) return x;
    var w = (tau * tau) / (tau * tau + se * se);
    return center + w * (x - center);
  }
  function ebTau2(values, ses) {
    var a = values.filter(function (x) { return x === x; });
    var s = ses.filter(function (x) { return x != null && x === x && x > 0; });
    if (a.length < 3) return 0;
    var m = a.reduce(function (p, x) { return p + x; }, 0) / a.length;
    var varr = a.reduce(function (p, x) { return p + (x - m) * (x - m); }, 0) / (a.length - 1);
    var mse = s.length ? s.reduce(function (p, x) { return p + x * x; }, 0) / s.length : 0;
    return Math.max(0, varr - mse);
  }
  function ebPosterior(value, se, center, tau2) {
    if (se == null || se <= 0 || tau2 == null || tau2 <= 0)
      return { mu: value, sd: (se != null && se > 0 ? se : 0), w: 1 };
    var w = tau2 / (tau2 + se * se);
    return { mu: center + w * (value - center), sd: Math.sqrt(w) * se, w: w };
  }
  function ewmaScore(prev, now, lam) {
    lam = (lam == null ? 0.5 : lam);
    if (prev == null || prev !== prev) return now;
    return lam * now + (1 - lam) * prev;
  }
  function compositeRankScore(tot, z, base, k, n, prev, lam, se) {
    k = (k == null ? 0.5 : k); lam = (lam == null ? 1 : lam);
    var sigma = (se != null && se === se && se > 0) ? se : convictionSigma(base, z);
    var s = lcbScore(tot, sigma, k);
    if (n != null && n >= 2) {
      var bar = Math.sqrt(2 * Math.log(n));
      if (bar > 0) s = s * Math.min(1, Math.abs(z) / bar);
    }
    return (prev != null) ? ewmaScore(prev, s, lam) : s;
  }
  var API = { grinoldKahn: grinoldKahn, alphaForecastSe: alphaForecastSe, convictionSigma: convictionSigma,
    lcbScore: lcbScore, deflatedConviction: deflatedConviction, steinShrink: steinShrink, ewmaScore: ewmaScore,
    compositeRankScore: compositeRankScore };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktRank = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
