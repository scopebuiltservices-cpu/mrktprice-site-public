/* volterm_engine.js — 1:1 JS port of volterm_engine.py (PDF 3). Retire sqrt-time vol scaling:
   horizon HV term structure + Lo-MacKinlay variance ratio (robust CI) + EWMA vol + blended scale.
   exports window.MrktVolTerm / module.exports. Research only, not advice. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktVolTerm = m;
})(this, function () {
  'use strict';
  function mean(x) { if (!x.length) return 0; var s = 0, i; for (i = 0; i < x.length; i++) s += x[i]; return s / x.length; }
  function vari(x, ddof) { if (ddof == null) ddof = 1; var n = x.length; if (n <= ddof) return 0; var m = mean(x), s = 0, i; for (i = 0; i < n; i++) s += (x[i] - m) * (x[i] - m); return s / (n - ddof); }

  function hvTermStructure(returns, horizons, overlapping) {
    if (overlapping == null) overlapping = true;
    var out = {}, T = returns.length, hi, H, t;
    for (hi = 0; hi < horizons.length; hi++) {
      H = horizons[hi];
      if (H <= 0 || T < H + 1) { out[H] = null; continue; }
      if (H === 1) { out[H] = Math.sqrt(vari(returns)); continue; }
      var sums = [];
      if (overlapping) {
        var run = 0; for (t = 0; t < H; t++) run += returns[t];
        sums.push(run);
        for (t = H; t < T; t++) { run += returns[t] - returns[t - H]; sums.push(run); }
      } else {
        for (t = 0; t + H <= T; t += H) { var s = 0, k; for (k = t; k < t + H; k++) s += returns[k]; sums.push(s); }
      }
      out[H] = sums.length > 1 ? Math.sqrt(vari(sums)) : null;
    }
    return out;
  }

  function sqrtBaseline(returns, horizons) {
    var s1 = Math.sqrt(vari(returns)), out = {}, i;
    for (i = 0; i < horizons.length; i++) { var H = horizons[i]; out[H] = H > 0 ? s1 * Math.sqrt(H) : null; }
    return out;
  }

  function varianceRatio(returns, q) {
    var T = returns.length;
    if (q < 2 || T < q + 1) return { vr: null, z: null, zRobust: null, ciLo: null, ciHi: null, q: q, n: T };
    var mu = mean(returns), i, t, j;
    var sa2 = 0; for (i = 0; i < T; i++) sa2 += (returns[i] - mu) * (returns[i] - mu); sa2 /= (T - 1);
    if (sa2 <= 0) return { vr: null, z: null, zRobust: null, ciLo: null, ciHi: null, q: q, n: T };
    var m = q * (T - q + 1) * (1.0 - q / T);
    var sc2 = 0;
    for (t = q - 1; t < T; t++) { var x = -q * mu, k; for (k = t - q + 1; k <= t; k++) x += returns[k]; sc2 += x * x; }
    sc2 /= m;
    var vr = sc2 / sa2;
    var vHomo = 2.0 * (2.0 * q - 1.0) * (q - 1.0) / (3.0 * q * T);
    var z = vHomo > 0 ? (vr - 1.0) / Math.sqrt(vHomo) : null;
    var dev2 = new Array(T); for (i = 0; i < T; i++) dev2[i] = (returns[i] - mu) * (returns[i] - mu);
    var sden = 0; for (i = 0; i < T; i++) sden += dev2[i]; var denom = sden * sden;
    var theta = 0;
    if (denom > 0) {
      for (j = 1; j < q; j++) {
        var num = 0; for (t = j; t < T; t++) num += dev2[t] * dev2[t - j];
        var deltaj = num / denom;
        theta += Math.pow(2.0 * (q - j) / q, 2) * deltaj;
      }
    }
    var zRob = theta > 0 ? (vr - 1.0) / Math.sqrt(theta) : null;
    var seRob = theta > 0 ? Math.sqrt(theta) : null;
    return { vr: vr, z: z, zRobust: zRob, ciLo: seRob ? vr - 1.96 * seRob : null,
      ciHi: seRob ? vr + 1.96 * seRob : null, q: q, n: T };
  }

  function ewmaVol(returns, lam, seed) {
    if (lam == null) lam = 0.94;
    if (!returns.length) return 0;
    var h = seed != null ? seed : vari(returns), i;
    for (i = 0; i < returns.length; i++) h = lam * h + (1 - lam) * returns[i] * returns[i];
    return Math.sqrt(Math.max(h, 0));
  }

  function studentize(yReal, yhat, sigmaH, gamma) { if (gamma == null) gamma = 1e-6; return (yReal - yhat) / (sigmaH + gamma); }

  function blendedScale(components, weights, H) {
    var keys = Object.keys(components).filter(function (k) { return components[k] != null && (weights[k] || 0) > 0; });
    if (!keys.length) return null;
    var wsum = 0, i; for (i = 0; i < keys.length; i++) wsum += weights[keys[i]];
    if (wsum <= 0) return null;
    var varH = 0; for (i = 0; i < keys.length; i++) varH += (weights[keys[i]] / wsum) * components[keys[i]] * components[keys[i]];
    return Math.sqrt(Math.max(varH, 0));
  }

  return { hvTermStructure: hvTermStructure, sqrtBaseline: sqrtBaseline, varianceRatio: varianceRatio,
    ewmaVol: ewmaVol, studentize: studentize, blendedScale: blendedScale };
});
