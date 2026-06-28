/* rank_engine.js — confidence-adjusted Bull/Bear ranking math, 1:1 port of tools/market_map/rank_engine.py.
   Locked to tools/rank_golden.json by tools/test_rank_parity.mjs. Exposes window.MrktRank (UMD). */
(function (root) {
  'use strict';
  function grinoldKahn(ic, sigma, z) { return ic * sigma * z; }
  function convictionSigma(base, z, floor, full) {
    floor = (floor == null ? 0.2 : floor); full = (full == null ? 1.5 : full);
    var rel = full > 0 ? Math.abs(z) / full : 0;
    rel = Math.max(floor, Math.min(1, rel));
    return rel > 0 ? base / rel : base;
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
  function steinShrink(x, se, tau) {
    if (se == null || se <= 0 || tau == null || tau <= 0) return x;
    var w = (tau * tau) / (tau * tau + se * se);
    return w * x;
  }
  function ewmaScore(prev, now, lam) {
    lam = (lam == null ? 0.5 : lam);
    if (prev == null || prev !== prev) return now;
    return lam * now + (1 - lam) * prev;
  }
  function compositeRankScore(tot, z, base, k, n, prev, lam) {
    k = (k == null ? 0.5 : k); lam = (lam == null ? 1 : lam);
    var s = lcbScore(tot, convictionSigma(base, z), k);
    return (prev != null) ? ewmaScore(prev, s, lam) : s;
  }
  var API = { grinoldKahn: grinoldKahn, convictionSigma: convictionSigma, lcbScore: lcbScore,
    deflatedConviction: deflatedConviction, steinShrink: steinShrink, ewmaScore: ewmaScore,
    compositeRankScore: compositeRankScore };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktRank = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
