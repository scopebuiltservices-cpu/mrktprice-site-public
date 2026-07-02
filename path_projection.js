/* path_projection.js — browser+Node port of tools/market_map/expectations_engine.path_projection.
 * Single source of truth for the Direction-Deck "Expected path" tile so the LIVE read equals the
 * server-published n.expA.proj decimal-for-decimal. Fuses the band's DISPERSION (champion sigma_H,
 * raw-VR corrected) and PERSISTENCE (Lo-MacKinlay VR significance) into: pathPct (% on the expected
 * path), expected TOP price (Maximum Favorable Excursion) timed before the OU half-life (theta), and
 * expected TOP volume (median x historical volume-elasticity). Verified against a committed Python
 * golden (test_pathproj_parity.mjs). Pure math, no deps. Research only. */
(function () {
  'use strict';
  var SQRT2 = Math.sqrt(2), TWO_PI = 2 * Math.PI;

  function erf(x) { // Abramowitz-Stegun 7.1.26 (max err ~1.5e-7)
    var t = 1 / (1 + 0.3275911 * Math.abs(x));
    var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return x >= 0 ? y : -y;
  }
  function ncdf(x) { return 0.5 * (1 + erf(x / SQRT2)); }

  function logrets(c) {
    var r = [], i;
    for (i = 1; i < c.length; i++) if (c[i] > 0 && c[i - 1] > 0) r.push(Math.log(c[i] / c[i - 1]));
    return r;
  }

  // metrics.variance_ratio_stat — Lo-MacKinlay (1988) heteroskedasticity-robust VR TEST
  function vrStat(closes, q) {
    var r = logrets(closes), T = r.length, i, k;
    if (T < q * 4 || q < 2) return null;
    var mu = 0; for (i = 0; i < T; i++) mu += r[i]; mu /= T;
    var dev = []; for (i = 0; i < T; i++) dev.push(r[i] - mu);
    var s2 = 0; for (i = 0; i < T; i++) s2 += dev[i] * dev[i]; s2 /= T; if (s2 <= 0) return null;
    var muq = q * mu, m = q * (T - q + 1) * (1.0 - q / T), sq = 0;
    for (i = 0; i <= T - q; i++) { var su = 0; for (k = 0; k < q; k++) su += r[i + k]; sq += (su - muq) * (su - muq); }
    var vq = sq / m, vr = vq / s2, s2sq = (T * s2) * (T * s2), theta = 0, j, t;
    for (j = 1; j < q; j++) { var num = 0; for (t = j; t < T; t++) num += dev[t] * dev[t] * dev[t - j] * dev[t - j]; var delta = s2sq > 0 ? num / s2sq : 0, w = 2.0 * (q - j) / q; theta += w * w * delta; }
    if (theta <= 0) return { vr: vr, z: null, p: null, q: q, n: T };
    var z = (vr - 1.0) / Math.sqrt(theta), p = 2.0 * (1.0 - ncdf(Math.abs(z)));
    return { vr: vr, z: z, p: p, q: q, n: T };
  }

  // metrics.half_life — OU mean-reversion half-life (dp on lagged log-price)
  function halfLife(closes, cap) {
    cap = cap || 252; var p = [], i;
    for (i = 0; i < closes.length; i++) if (closes[i] > 0) p.push(Math.log(closes[i]));
    if (p.length < 25) return null;
    var dp = [], lag = []; for (i = 1; i < p.length; i++) { dp.push(p[i] - p[i - 1]); lag.push(p[i - 1]); }
    var n = dp.length, mx = 0, my = 0; for (i = 0; i < n; i++) { mx += lag[i]; my += dp[i]; } mx /= n; my /= n;
    var sxy = 0, sxx = 0; for (i = 0; i < n; i++) { sxy += (lag[i] - mx) * (dp[i] - my); sxx += (lag[i] - mx) * (lag[i] - mx); }
    if (sxx <= 0) return null; var b = sxy / sxx;
    if (!(b < 0)) return null; var h = Math.log(2) / (-b);
    return h > 0 ? Math.min(h, cap) : null;
  }

  // expectations_engine._champion_sigma — sigma_d*sqrt(H*VR), RAW variance ratio (biased v1, len denom)
  function championSigma(closes, H) {
    var c = [], i; for (i = 0; i < closes.length; i++) if (closes[i] > 0) c.push(closes[i]);
    if (c.length < 30) return null;
    var r = []; for (i = 1; i < c.length; i++) r.push(Math.log(c[i] / c[i - 1]));
    var m = 0; for (i = 0; i < r.length; i++) m += r[i]; m /= r.length;
    var v = 0; for (i = 0; i < r.length; i++) v += (r[i] - m) * (r[i] - m); v /= (r.length - 1);
    var sd = Math.sqrt(v); if (sd <= 0) return null;
    var q = Math.min(H, Math.max(2, (c.length / 4) | 0));
    if (r.length < q * 4) return sd * Math.sqrt(H);
    var v1 = 0; for (i = 0; i < r.length; i++) v1 += (r[i] - m) * (r[i] - m); v1 /= r.length;
    if (v1 <= 0) return sd * Math.sqrt(H);
    var s = 0, k; for (k = q - 1; k < r.length; k++) { var su = 0; for (i = 0; i < q; i++) su += r[k - i]; s += (su - q * m) * (su - q * m); }
    s /= (r.length - q + 1);
    var vr = s / (q * v1);
    return sd * Math.sqrt(H * (vr > 0 ? vr : 1.0));
  }

  // path_probability.touch_up + expected_max_favorable (Simpson)
  function touchUp(b, s, m) {
    if (s <= 0) return b <= 0 ? 1 : 0; if (b <= 0) return 1;
    return Math.min(1, ncdf((m - b) / s) + Math.exp(2 * m * b / (s * s)) * ncdf((-b - m) / s));
  }
  function mfe(s, m) {
    if (s <= 0) return Math.max(0, m);
    if (Math.abs(m) < 1e-15) return s * Math.sqrt(2 / Math.PI);
    var hi = Math.max(0, m) + 12 * s, n = 2000, h = hi / n, i, tot;
    function ge(b) { return b > 0 ? touchUp(b, s, m) : 1; }
    tot = ge(0) + ge(hi); for (i = 1; i < n; i++) tot += (i % 2 ? 4 : 2) * ge(i * h);
    return tot * h / 3;
  }
  function olsSlope(xs, ys) {
    var n = xs.length, i; if (n < 5) return null;
    var mx = 0, my = 0; for (i = 0; i < n; i++) { mx += xs[i]; my += ys[i]; } mx /= n; my /= n;
    var sxy = 0, sxx = 0; for (i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) * (xs[i] - mx); }
    return sxx > 0 ? sxy / sxx : null;
  }
  function r6(x) { return Math.round(x * 1e6) / 1e6; }

  function project(closes, vols, H, r) {
    H = H || 21; r = r || 5;
    var c = [], i; for (i = 0; i < (closes || []).length; i++) { var x = +closes[i]; if (x > 0) c.push(x); }
    if (c.length < 60) return null;
    var lr = logrets(c); if (lr.length < 40) return null;
    var mu = 0; for (i = 0; i < lr.length; i++) mu += lr[i]; mu /= lr.length;
    var sd_d = Math.sqrt(lr.reduce(function (a, x) { return a + (x - mu) * (x - mu); }, 0) / (lr.length - 1));
    if (sd_d <= 0) return null;
    var sH = championSigma(c, H); if (!sH || sH <= 0) return null;
    var q = Math.min(H, Math.max(2, (c.length / 4) | 0));
    var vs = vrStat(c, q), vr = vs ? vs.vr : 1.0, z = vs ? vs.z : null;
    var sig = !!(z != null && Math.abs(z) >= 1.6449);
    var hl = halfLife(c, 252);
    var tail = 0; for (i = Math.max(0, lr.length - r); i < lr.length; i++) tail += lr[i];
    var push = tail > 0 ? 1 : (tail < 0 ? -1 : 1), dir, kappa;
    if (sig && vr > 1) { dir = push; kappa = Math.min(0.5, vr - 1.0); }
    else if (sig && vr < 1) { dir = -push; kappa = Math.min(0.5, 1.0 - vr); }
    else { dir = push; kappa = 0.0; }
    var driftH = dir * kappa * sH, p_dir = ncdf(Math.abs(driftH) / sH);
    var exc = mfe(sH, Math.abs(driftH)), P0 = c[c.length - 1], peakLog = dir * exc;
    var ttp = (hl != null && vr < 1) ? Math.max(1.0, Math.min(H, hl)) : H;
    var topVol = null, volMult = null, volOK = false;
    if (vols) {
      var v = []; for (i = 0; i < vols.length; i++) { var vv = +vols[i]; if (vv > 0) v.push(vv); }
      if (v.length >= 40 && v.length >= lr.length) {
        var av = [], lv = [];
        for (i = 0; i < lr.length; i++) { av.push(Math.abs(lr[i]) / sd_d); lv.push(Math.log(v[v.length - lr.length + i])); }
        var beta = olsSlope(av, lv), sv = v.slice().sort(function (a, b) { return a - b; }), medv = sv[sv.length >> 1];
        if (beta != null && beta > 0) {
          var peakDaily = (Math.abs(peakLog) / ttp) / sd_d;
          volMult = Math.max(1.0, Math.min(Math.exp(beta * peakDaily), 8.0));
          topVol = medv * volMult; volOK = true;
        }
      }
    }
    return {
      sigmaH: r6(sH), driftH: r6(driftH), dir: (dir | 0),
      pathPct: Math.round(1000 * p_dir) / 10, pathDir: (dir > 0 ? 'up' : 'down'),
      vr: Math.round(vr * 1000) / 1000, z: (z != null ? Math.round(z * 100) / 100 : null), halfLife: (hl ? Math.round(hl * 10) / 10 : null),
      peakPrice: Math.round(P0 * Math.exp(peakLog) * 1e4) / 1e4, peakPct: Math.round((Math.exp(peakLog) - 1.0) * 1e4) / 100,
      peakLogExc: r6(exc), timeToPeakD: Math.round(ttp * 10) / 10,
      topVolume: (topVol ? Math.round(topVol) : null), topVolMult: (volMult ? Math.round(volMult * 100) / 100 : null),
      volElastOK: volOK, smart: sig
    };
  }

  var API = { project: project, championSigma: championSigma, vrStat: vrStat, halfLife: halfLife, mfe: mfe, touchUp: touchUp, olsSlope: olsSlope, ncdf: ncdf };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (typeof window !== 'undefined') window.PathProj = API;
})();
