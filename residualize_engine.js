/* residualize_engine.js — 1:1 JS port of residualize_engine.py. Fama-French residualization:
   strip compensated factor exposure (Mkt/SMB/HML/RMW/CMA/Mom) from a raw alpha to leave selection edge.
   exports window.MrktResid / module.exports. Research only, not advice. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktResid = m;
})(this, function () {
  'use strict';
  var FACTORS = ["MktRF", "SMB", "HML", "RMW", "CMA", "Mom"];

  function solve(A, b) {
    var n = b.length, M = [], i, c, r, k;
    for (i = 0; i < n; i++) M.push(A[i].slice().concat([b[i]]));
    for (c = 0; c < n; c++) {
      var p = c;
      for (r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      if (Math.abs(M[p][c]) < 1e-15) return null;
      var tmp = M[c]; M[c] = M[p]; M[p] = tmp;
      var piv = M[c][c];
      for (r = 0; r < n; r++) {
        if (r === c) continue;
        var f = M[r][c] / piv;
        if (f !== 0) for (k = c; k <= n; k++) M[r][k] -= f * M[c][k];
      }
    }
    var x = new Array(n);
    for (i = 0; i < n; i++) x[i] = M[i][n] / M[i][i];
    return x;
  }

  function multivarOls(X, y, ridge) {
    if (ridge == null) ridge = 1e-8;
    var T = y.length;
    if (T === 0 || !X.length) return { coef: [], residSd: 0, r2: 0, n: 0 };
    var K = X[0].length, i, j, t;
    var XtX = [], Xty = new Array(K).fill(0);
    for (i = 0; i < K; i++) XtX.push(new Array(K).fill(0));
    for (t = 0; t < T; t++) {
      var xt = X[t];
      for (i = 0; i < K; i++) {
        Xty[i] += xt[i] * y[t];
        var xi = xt[i], row = XtX[i];
        for (j = 0; j < K; j++) row[j] += xi * xt[j];
      }
    }
    for (i = 0; i < K; i++) XtX[i][i] += ridge;
    var coef = solve(XtX, Xty) || new Array(K).fill(0);
    var ybar = 0; for (t = 0; t < T; t++) ybar += y[t]; ybar /= T;
    var sse = 0, sst = 0;
    for (t = 0; t < T; t++) {
      var pred = 0; for (i = 0; i < K; i++) pred += coef[i] * X[t][i];
      sse += (y[t] - pred) * (y[t] - pred);
      sst += (y[t] - ybar) * (y[t] - ybar);
    }
    var dof = Math.max(1, T - K);
    return { coef: coef, residSd: Math.sqrt(sse / dof), r2: sst > 0 ? (1 - sse / sst) : 0, n: T };
  }

  function factorBetas(nameExcess, factorRows, factors, ridge) {
    factors = factors || FACTORS; if (ridge == null) ridge = 1e-8;
    var X = [], y = [], i, k;
    for (i = 0; i < factorRows.length; i++) {
      var ne = nameExcess[i];
      if (ne == null) continue;
      var vals = [], ok = true;
      for (k = 0; k < factors.length; k++) { var v = factorRows[i][factors[k]]; if (v == null) { ok = false; break; } vals.push(v); }
      if (!ok) continue;
      X.push([1.0].concat(vals)); y.push(ne);
    }
    var betas = {};
    if (y.length < factors.length + 2) {
      for (k = 0; k < factors.length; k++) betas[factors[k]] = 0;
      return { alpha: 0, betas: betas, residSd: 0, r2: 0, n: y.length };
    }
    var res = multivarOls(X, y, ridge), c = res.coef;
    for (k = 0; k < factors.length; k++) betas[factors[k]] = c[k + 1];
    return { alpha: c[0], betas: betas, residSd: res.residSd, r2: res.r2, n: res.n };
  }

  function factorPremia(factorRows, factors, halflife) {
    factors = factors || FACTORS;
    var out = {}, k;
    for (k = 0; k < factors.length; k++) {
      var f = factors[k], vals = [];
      for (var i = 0; i < factorRows.length; i++) { var v = factorRows[i][f]; if (v != null) vals.push(v); }
      if (!vals.length) { out[f] = 0; continue; }
      if (halflife && halflife > 0) {
        var lam = Math.pow(0.5, 1.0 / halflife), num = 0, den = 0, w = 1.0;
        for (var j = vals.length - 1; j >= 0; j--) { num += w * vals[j]; den += w; w *= lam; }
        out[f] = den > 0 ? num / den : 0;
      } else {
        var s = 0; for (var m = 0; m < vals.length; m++) s += vals[m]; out[f] = s / vals.length;
      }
    }
    return out;
  }

  function residualize(alphaRaw, betas, premia, horizon, factors) {
    factors = factors || FACTORS; if (horizon == null) horizon = 21;
    var fe = 0, contrib = {}, k;
    for (k = 0; k < factors.length; k++) {
      var f = factors[k], c = horizon * (betas[f] || 0) * (premia[f] || 0);
      fe += c; contrib[f] = c;
    }
    return { muResid: alphaRaw - fe, alphaRaw: alphaRaw, factorExpected: fe, contrib: contrib };
  }

  return { FACTORS: FACTORS, multivarOls: multivarOls, factorBetas: factorBetas,
    factorPremia: factorPremia, residualize: residualize };
});
