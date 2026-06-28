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
  // ---- "Omitted Strategies" extensions (1:1 mirror of rank_engine.py) ----
  function effectiveBreadth(n, avgCorr) {
    if (n == null || n < 1) return 1;
    var rho = (avgCorr == null || avgCorr !== avgCorr) ? 0 : Math.max(0, Math.min(0.999, avgCorr));
    return Math.max(1, n / (1 + (n - 1) * rho));
  }
  function enbEntropy(spectrum) {
    var s = spectrum.filter(function (x) { return x === x && x > 0; });
    var tot = s.reduce(function (p, x) { return p + x; }, 0);
    if (tot <= 0 || !s.length) return 1;
    var h = 0; s.forEach(function (x) { var pi = x / tot; h -= pi * Math.log(pi); });
    return Math.exp(h);
  }
  function tradingCost(volPct, feeBps, halfSpreadBps, participation, impactCoef) {
    feeBps = (feeBps == null ? 2 : feeBps); participation = (participation == null ? 0.05 : participation); impactCoef = (impactCoef == null ? 0.1 : impactCoef);
    var fee = feeBps / 100;
    var v = (volPct && volPct === volPct) ? volPct : 2;
    var hs = (halfSpreadBps != null) ? halfSpreadBps / 100 : 0.05 * v;
    var impact = impactCoef * v * Math.sqrt(Math.max(participation, 0));
    return 2 * (fee + hs) + impact;
  }
  function netAlpha(mu, cost) { if (cost == null || cost < 0) cost = 0; return mu >= 0 ? mu - cost : mu + cost; }
  function cvarEs(returns, alpha) {
    alpha = (alpha == null ? 0.05 : alpha);
    var r = returns.filter(function (x) { return x === x; }).sort(function (a, b) { return a - b; });
    if (r.length < 20) return null;
    var k = Math.max(1, Math.floor(alpha * r.length));
    var tail = r.slice(0, k);
    return Math.abs(tail.reduce(function (p, x) { return p + x; }, 0) / tail.length);
  }
  function tailAdjust(mu, es, lam) { lam = (lam == null ? 0.1 : lam); if (es == null || es < 0) return mu; return mu >= 0 ? mu - lam * es : mu + lam * es; }
  function decayAlpha(mu, horizon, halfLife) { if (!halfLife || halfLife <= 0 || horizon == null || horizon < 0) return mu; return mu * Math.pow(0.5, horizon / halfLife); }
  function transitionGate(prev, now, band) { if (prev == null || prev !== prev) return now; if (band == null || band < 0) band = 0; return Math.abs(now - prev) > band ? now : prev; }
  function _lwCov(Xc) {
    var T = Xc.length, p = Xc[0].length, S = [];
    for (var i = 0; i < p; i++) S.push(new Array(p).fill(0));
    for (var t = 0; t < T; t++) { var x = Xc[t]; for (i = 0; i < p; i++) { var xi = x[i], row = S[i]; for (var j = 0; j < p; j++) row[j] += xi * x[j]; } }
    for (i = 0; i < p; i++) for (j = 0; j < p; j++) S[i][j] /= T;
    return S;
  }
  function ledoitWolf(X) {
    var T = X.length, p = X[0].length, i, j, t;
    var mean = []; for (j = 0; j < p; j++) { var m = 0; for (t = 0; t < T; t++) m += X[t][j]; mean.push(m / T); }
    var Xc = []; for (t = 0; t < T; t++) { var row = []; for (j = 0; j < p; j++) row.push(X[t][j] - mean[j]); Xc.push(row); }
    var S = _lwCov(Xc);
    var mm = 0; for (i = 0; i < p; i++) mm += S[i][i]; mm /= p;
    var d2 = 0; for (i = 0; i < p; i++) for (j = 0; j < p; j++) { var df = S[i][j] - (i === j ? mm : 0); d2 += df * df; } d2 /= p;
    var bb = 0; for (t = 0; t < T; t++) { var xx = Xc[t]; for (i = 0; i < p; i++) for (j = 0; j < p; j++) { var e = xx[i] * xx[j] - S[i][j]; bb += e * e; } }
    bb = bb / (T * T) / p;
    var b2 = Math.min(bb, d2), delta = d2 > 0 ? b2 / d2 : 0; delta = Math.max(0, Math.min(1, delta));
    var Sig = []; for (i = 0; i < p; i++) { var r2 = []; for (j = 0; j < p; j++) r2.push(delta * (i === j ? mm : 0) + (1 - delta) * S[i][j]); Sig.push(r2); }
    return { delta: delta, sigma: Sig };
  }
  function _ncdfR(x) { return 0.5 * (1 + (function (z) { var s = z < 0 ? -1 : 1; z = Math.abs(z); var t = 1 / (1 + 0.3275911 * z); var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z); return s * y; })(x / Math.SQRT2)); }
  function _nppfR(pp) {
    var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
    var b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
    var c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
    var d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00], pl = 0.02425, q, r;
    if (pp < pl) { q = Math.sqrt(-2 * Math.log(pp)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (pp <= 1 - pl) { q = pp - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); }
    q = Math.sqrt(-2 * Math.log(1 - pp)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  function deflatedSharpe(sr, T, skew, kurt, nTrials) {
    skew = (skew == null ? 0 : skew); kurt = (kurt == null ? 3 : kurt); nTrials = (nTrials == null ? 1 : nTrials);
    if (T < 3) return null;
    var varSr = (1 - skew * sr + (kurt - 1) / 4 * sr * sr) / (T - 1), srStar = 0;
    if (nTrials >= 2) { var g = 0.5772156649015329; srStar = Math.sqrt(Math.max(varSr, 0)) * ((1 - g) * _nppfR(1 - 1 / nTrials) + g * _nppfR(1 - 1 / (nTrials * Math.E))); }
    return _ncdfR((sr - srStar) / Math.sqrt(Math.max(varSr, 1e-12)));
  }
  var API = { grinoldKahn: grinoldKahn, alphaForecastSe: alphaForecastSe, convictionSigma: convictionSigma,
    effectiveBreadth: effectiveBreadth, enbEntropy: enbEntropy, tradingCost: tradingCost, netAlpha: netAlpha,
    cvarEs: cvarEs, tailAdjust: tailAdjust, decayAlpha: decayAlpha, transitionGate: transitionGate,
    ledoitWolf: ledoitWolf, deflatedSharpe: deflatedSharpe,
    lcbScore: lcbScore, deflatedConviction: deflatedConviction, steinShrink: steinShrink,
    ebTau2: ebTau2, ebPosterior: ebPosterior, ewmaScore: ewmaScore,
    compositeRankScore: compositeRankScore };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktRank = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
