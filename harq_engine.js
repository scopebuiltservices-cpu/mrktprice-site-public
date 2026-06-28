/* harq_engine.js — CORRECTED HARQ (Bollerslev-Patton-Quaedvlieg 2016) realized-vol forecaster, 1:1 port of
   tools/market_map/harq_regime.py. The daily coefficient is measurement-error adjusted via the sqrtRQ~ x RVd
   INTERACTION (not an additive log-RQ regressor); adds walk-forward OOS R^2 and a split-conformal quantile on
   HARQ's OWN out-of-sample residuals. Locked to tools/harq_golden.json by tools/test_harq_parity.mjs.
   Exposes window.MrktHARQ.forecast(closes). Pure, no deps. */
(function (root) {
  'use strict';
  var FLOOR = 1e-12;
  function ols(X, y) {
    var n = X.length, p = X[0].length, i, a, b, c, r, j;
    var XtX = [], Xty = [];
    for (a = 0; a < p; a++) { XtX.push(new Array(p).fill(0)); Xty.push(0); }
    for (i = 0; i < n; i++) { var xi = X[i], yi = y[i]; for (a = 0; a < p; a++) { Xty[a] += xi[a] * yi; var xa = xi[a], row = XtX[a]; for (b = 0; b < p; b++) row[b] += xa * xi[b]; } }
    var A = [];
    for (i = 0; i < p; i++) { var rr = XtX[i].slice(); for (j = 0; j < p; j++) rr.push(i === j ? 1 : 0); A.push(rr); }
    for (c = 0; c < p; c++) {
      var pv = c;
      for (r = c + 1; r < p; r++) if (Math.abs(A[r][c]) > Math.abs(A[pv][c])) pv = r;
      if (Math.abs(A[pv][c]) < 1e-300) return null;
      var tmp = A[c]; A[c] = A[pv]; A[pv] = tmp; var d = A[c][c];
      for (j = 0; j < 2 * p; j++) A[c][j] /= d;
      for (r = 0; r < p; r++) { if (r === c) continue; var f = A[r][c]; for (j = 0; j < 2 * p; j++) A[r][j] -= f * A[c][j]; }
    }
    var inv = A.map(function (rw) { return rw.slice(p); });
    var beta = [];
    for (a = 0; a < p; a++) { var s = 0; for (b = 0; b < p; b++) s += inv[a][b] * Xty[b]; beta.push(s); }
    return beta;
  }
  function r2of(X, y, beta) {
    var n = y.length, i, a, ybar = 0; for (i = 0; i < n; i++) ybar += y[i]; ybar /= n;
    var sst = 0, sse = 0; for (i = 0; i < n; i++) sst += (y[i] - ybar) * (y[i] - ybar);
    sst = sst || 1e-300;
    for (i = 0; i < n; i++) { var yh = 0; for (a = 0; a < beta.length; a++) yh += X[i][a] * beta[a]; sse += (y[i] - yh) * (y[i] - yh); }
    return 1 - sse / sst;
  }
  function logrets(c) { var o = []; for (var i = 1; i < c.length; i++) o.push((c[i - 1] > 0 && c[i] > 0) ? Math.log(c[i] / c[i - 1]) : 0); return o; }
  function median(xs) { var s = xs.slice().sort(function (a, b) { return a - b; }), n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2])) : 0; }
  function mad(xs, m) { return xs.length ? 1.4826 * median(xs.map(function (x) { return Math.abs(x - m); })) : 0; }
  function quantile(xs, q) { var s = xs.slice().sort(function (a, b) { return a - b; }); if (!s.length) return 0; var pos = q * (s.length - 1), lo = Math.floor(pos), hi = Math.ceil(pos); return lo === hi ? s[lo] : s[lo] + (s[hi] - s[lo]) * (pos - lo); }

  function forecast(closes, ann) {
    ann = ann || 252;
    var r = logrets(closes);
    if (r.length < 60) return null;
    var rv = r.map(function (x) { return Math.max(x * x, FLOOR); });
    var n = rv.length, t;
    function rq(t) { var w = r.slice(Math.max(0, t - 4), t + 1), m = w.length, s = 0; for (var i = 0; i < m; i++) s += Math.pow(w[i], 4); return m ? Math.max((m / 3) * s, FLOOR) : FLOOR; }
    var srq = []; for (t = 0; t < n; t++) srq.push(Math.sqrt(rq(t)));
    var srqbar = 0, cnt = 0; for (t = 22; t < n; t++) { srqbar += srq[t]; cnt++; } srqbar /= Math.max(1, cnt);
    function pHv(t) {
      var hist = []; for (var i = Math.max(0, t - 120); i < t; i++) hist.push(Math.log(rv[i]));
      if (hist.length < 20) return 0.5;
      var m = median(hist), sd = mad(hist, m) || 1e-9;
      return 1 / (1 + Math.exp(-(Math.log(rv[t]) - m) / sd));
    }
    function rowAt(t) { var rvd = rv[t - 1], rvw = 0, rvm = 0, i; for (i = t - 5; i < t; i++) rvw += rv[i]; rvw /= 5; for (i = t - 22; i < t; i++) rvm += rv[i]; rvm /= 22; var sq = srq[t - 1] - srqbar; return [1, rvd, sq * rvd, rvw, rvm, pHv(t - 1)]; }
    var X = [], Y = []; for (t = 22; t < n; t++) { X.push(rowAt(t)); Y.push(rv[t]); }
    if (X.length < 30) return null;
    var beta = ols(X, Y); if (!beta) return null;
    var r2 = r2of(X, Y, beta);
    var cut = Math.floor(X.length * 0.7), oosR2 = NaN, confQ = null;
    if (cut >= 30 && X.length - cut >= 10) {
      var btr = ols(X.slice(0, cut), Y.slice(0, cut));
      if (btr) {
        var ybar = 0, i; for (i = 0; i < cut; i++) ybar += Y[i]; ybar /= cut;
        var sseM = 0, sse0 = 0, resid = [];
        for (i = cut; i < X.length; i++) {
          var pred = 0, a; for (a = 0; a < btr.length; a++) pred += X[i][a] * btr[a]; pred = Math.max(pred, FLOOR);
          sseM += (Y[i] - pred) * (Y[i] - pred); sse0 += (Y[i] - ybar) * (Y[i] - ybar);
          var sd = Math.sqrt(pred) || 1e-9; resid.push(Math.abs(Math.sqrt(Y[i]) - Math.sqrt(pred)) / sd);
        }
        oosR2 = sse0 > 0 ? 1 - sseM / sse0 : NaN;
        if (resid.length) confQ = quantile(resid, 0.90);
      }
    }
    var rvw = 0, rvm = 0, i2; for (i2 = n - 5; i2 < n; i2++) rvw += rv[i2]; rvw /= 5; for (i2 = n - 22; i2 < n; i2++) rvm += rv[i2]; rvm /= 22;
    var xf = [1, rv[n - 1], (srq[n - 1] - srqbar) * rv[n - 1], rvw, rvm, pHv(n - 1)];
    var rvf = 0, a2; for (a2 = 0; a2 < beta.length; a2++) rvf += xf[a2] * beta[a2]; rvf = Math.max(rvf, FLOOR);
    var volDaily = Math.sqrt(rvf);
    var c20 = 0, k; for (k = n - 20; k < n; k++) c20 += rv[k]; c20 /= 20;
    return {
      rvForecast: rvf, volDaily: volDaily, volForecastAnn: volDaily * Math.sqrt(ann) * 100,
      curVolAnn: Math.sqrt(rv[n - 1]) * Math.sqrt(ann) * 100, cur20VolAnn: Math.sqrt(c20) * Math.sqrt(ann) * 100,
      r2: r2, oosR2: (oosR2 !== oosR2 ? null : oosR2), confQ: confQ, n: X.length, beta: beta, b1Q: beta[2], phvNow: xf[5],
      comp: { rvD: rv[n - 1], rvW: rvw, rvM: rvm, sqrtRQz: srq[n - 1] - srqbar },
      labels: ['const', 'RVd', 'sqrtRQ~*RVd (HARQ)', 'RVw', 'RVm', 'p(high-vol)']
    };
  }
  var API = { forecast: forecast };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktHARQ = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
