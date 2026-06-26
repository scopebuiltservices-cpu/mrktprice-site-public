/* MrktPrice shared stat engine — the SINGLE SOURCE OF TRUTH for the parity-critical estimators.
   Loaded by terminal.html as <script src="engine.js"> (attaches bare globals for the inline code)
   and imported by tools/test_stats_parity.mjs (via globalThis.MrktEngine) so the cross-language
   "verified vs Python" test checks THIS file, not a drifting copy. Classic UMD script (no import/
   export) so it runs identically in the browser and in Node. Pure functions, no DOM. Research only.

   Contents: _ols (OLS via normal equations + Gauss-Jordan), _mackinnonCV (ADF 5% surface),
   adfTest (AIC-lag ADF, regression-rows T + small-sample flag), _nwlrv (Newey-West LRV),
   kpssTest (KPSS level + small-sample flag). Mirrored 1:1 by tools/market_map/stats_ref.py. */
(function (root) {
  'use strict';

  function _ols(X, y) {
    const n = X.length, p = X[0].length; const XtX = Array.from({ length: p }, () => new Array(p).fill(0)), Xty = new Array(p).fill(0);
    for (let i = 0; i < n; i++) { for (let a = 0; a < p; a++) { Xty[a] += X[i][a] * y[i]; for (let b = 0; b < p; b++) XtX[a][b] += X[i][a] * X[i][b]; } }
    const A = XtX.map((row, i) => row.concat(Array.from({ length: p }, (_, j) => i === j ? 1 : 0)));
    for (let c = 0; c < p; c++) { let pv = c; for (let r = c + 1; r < p; r++) if (Math.abs(A[r][c]) > Math.abs(A[pv][c])) pv = r; if (Math.abs(A[pv][c]) < 1e-300) return null;[A[c], A[pv]] = [A[pv], A[c]]; const d = A[c][c]; for (let j = 0; j < 2 * p; j++) A[c][j] /= d; for (let r = 0; r < p; r++) { if (r === c) continue; const f = A[r][c]; for (let j = 0; j < 2 * p; j++) A[r][j] -= f * A[c][j]; } }
    const inv = A.map(row => row.slice(p)); const beta = new Array(p).fill(0); for (let a = 0; a < p; a++) for (let b = 0; b < p; b++) beta[a] += inv[a][b] * Xty[b];
    let sse = 0; for (let i = 0; i < n; i++) { let yh = 0; for (let a = 0; a < p; a++) yh += X[i][a] * beta[a]; sse += (y[i] - yh) * (y[i] - yh); } const s2 = sse / Math.max(1, n - p); const se = inv.map((row, a) => Math.sqrt(Math.max(s2 * row[a], 0))); return { beta, se };
  }
  function _mackinnonCV(T, lvl) { /* MacKinnon (1996) response surface, intercept-only: CV = b0 + b1/T + b2/T^2 */
    const P = { '1': [-3.43035, -6.5393, -16.786], '5': [-2.86154, -2.8903, -4.234], '10': [-2.56677, -1.5384, -2.809] }; const b = P[lvl]; return b[0] + b[1] / T + b[2] / (T * T);
  }
  function adfTest(y) {
    const n = y.length; if (n < 25) return { tstat: null, reject: null, lag: null, cv5: null }; const dy = []; for (let i = 1; i < n; i++) dy.push(y[i] - y[i - 1]);
    const pmax = Math.max(0, Math.min(Math.floor(12 * Math.pow(n / 100, 0.25)), Math.floor((dy.length - 2) / 2))); let best = null;
    for (let lag = 0; lag <= pmax; lag++) { const X = [], t = []; for (let k = pmax + 1; k < dy.length; k++) { const row = [1, y[k]]; for (let i = 1; i <= lag; i++) row.push(dy[k - i]); X.push(row); t.push(dy[k]); }
      if (t.length < 10) continue; const o = _ols(X, t); if (!o) continue; let ssr = 0; for (let i = 0; i < t.length; i++) { let yh = 0; for (let j = 0; j < X[i].length; j++) yh += X[i][j] * o.beta[j]; ssr += (t[i] - yh) * (t[i] - yh); }
      const mm = t.length, kk = X[0].length, aic = mm * Math.log(ssr / mm + 1e-300) + 2 * kk; if (!best || aic < best.aic) best = { aic, o, lag }; }
    if (!best) return { tstat: null, reject: null, lag: null, cv5: null }; const ts = best.o.se[1] > 0 ? best.o.beta[1] / best.o.se[1] : 0; const _T = Math.max(dy.length - (pmax + 1), 10); const cv5 = _mackinnonCV(_T, '5');
    return { tstat: ts, lag: best.lag, cv5, reject: ts < cv5, n: _T, small: _T < 80 };   // small: asymptotic CV unreliable below ~80 obs (H4)
  }
  function _nwlrv(u) { const n = u.length; const L = Math.floor(4 * Math.pow(n / 100, 2 / 9)); let g0 = 0; for (let i = 0; i < n; i++) g0 += u[i] * u[i]; g0 /= n; let s = g0; for (let j = 1; j <= L; j++) { let gj = 0; for (let i = j; i < n; i++) gj += u[i] * u[i - j]; gj /= n; s += 2 * (1 - j / (L + 1)) * gj; } return s; }
  function kpssTest(y) { const n = y.length; if (n < 25) return { eta: null, reject: null }; const m = y.reduce((a, b) => a + b, 0) / n, e = y.map(v => v - m); let S = 0, ss = 0; for (const v of e) { S += v; ss += S * S; } const lrv = Math.max(1e-300, _nwlrv(e)); const eta = ss / (n * n * lrv); return { eta, reject: eta > 0.463, n, small: n < 80 }; }   // small: KPSS over-rejects below ~80 obs (H4)

  /* ---- engine-private primitives (terminal keeps its own lr/vr/sd for its other inline code) ---- */
  function _lr(c) { const r = []; for (let i = 1; i < c.length; i++) r.push(Math.log(c[i] / c[i - 1])); return r; }
  function _vr(a) { const m = a.reduce((x, y) => x + y, 0) / a.length; return a.reduce((s, y) => s + (y - m) * (y - m), 0) / (a.length - 1); }
  function _sd(a) { return Math.sqrt(_vr(a)); }

  /* ---- EMA ---- */
  function ema(c, N) { const a = 2 / (N + 1); let e = c[0]; const o = [e]; for (let i = 1; i < c.length; i++) { e = a * c[i] + (1 - a) * e; o.push(e); } return o; }
  function emaProjPath(slope, P0, H, phi) { const path = []; let cum = 0; for (let h = 1; h <= H; h++) { cum += Math.pow(phi, h - 1); path.push({ t: h, price: P0 + slope * cum }); } return path; }

  /* ---- realized volatility (rolling, annualized) ---- */
  function hvRollSeries(r, w) { const o = []; for (let i = w; i <= r.length; i++) { o.push(_sd(r.slice(i - w, i)) * Math.sqrt(252)); } return o; }

  /* ---- 3x3 matrix inverse (GARCH observed-information SEs) ---- */
  function _inv3(A) { const a = A[0][0], b = A[0][1], c = A[0][2], d = A[1][0], e = A[1][1], f = A[1][2], g = A[2][0], h = A[2][1], i = A[2][2];
    const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g); if (!isFinite(det) || Math.abs(det) < 1e-300) return null; const id = 1 / det;
    return [[(e * i - f * h) * id, (c * h - b * i) * id, (b * f - c * e) * id], [(f * g - d * i) * id, (a * i - c * g) * id, (c * d - a * f) * id], [(d * h - e * g) * id, (b * g - a * h) * id, (a * e - b * d) * id]]; }

  /* ---- GARCH(1,1) QMLE. opts.seed: 'uncond' (default — h0 = sample unconditional variance, the
         historical behavior) or 'stationary' (h0 = w/(1-a-b), parameter-consistent; see the backtest
         harness tools/test_garch_seed_backtest.mjs before enabling it live). ---- */
  function garch(r, opts) {
    var SEED = (opts && opts.seed) || 'uncond'; const uv = _vr(r), n = r.length;
    function h0of(w, a, b) { return (SEED === 'stationary' && (1 - a - b) > 1e-6) ? w / (1 - a - b) : uv; }
    function nll(w, a, b) { let h = h0of(w, a, b), ll = 0; for (let t = 0; t < n; t++) { if (t > 0) h = w + a * r[t - 1] * r[t - 1] + b * h; if (h <= 1e-16) return 1e12; ll += Math.log(h) + r[t] * r[t] / h; } return .5 * ll; }
    let best = { w: .05 * uv, a: .05, b: .9, ll: 1e18 }; const grid = []; const tp = (w, a, b) => { if (w <= 0 || a < 0 || b <= 0 || a + b >= .9999) return; const v = nll(w, a, b); grid.push({ k: a + b, ll: v }); if (v < best.ll) best = { w, a, b, ll: v }; };
    for (let k = .5; k <= .995; k += .005) for (let a = 0; a <= Math.min(.3, k); a += .01) { const b = k - a; for (const f of [.3, 1, 3, 10]) tp(f * (1 - k) * uv, a, b); }
    for (let it = 0; it < 6; it++) { const s = .004 / (it + 1), sf = Math.max(best.w * .4 / (it + 1), 1e-12); for (const dw of [-sf, 0, sf]) for (const da of [-s, 0, s]) for (const db of [-s, 0, s]) tp(best.w + dw, best.a + da, best.b + db); }
    const tol = best.ll + 1, within = grid.filter(g => g.ll <= tol).map(g => g.k); const kLo = Math.min(...within), kHi = Math.max(...within), kappa = best.a + best.b;
    const xo = [best.w, best.a, best.b], hs = [Math.max(best.w * 1e-3, 1e-9), 1e-4, 1e-4], _f = p => nll(p[0], p[1], p[2]), Hn = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) { const pp = xo.slice(), pm = xo.slice(), mp = xo.slice(), mm = xo.slice(); pp[i] += hs[i]; pp[j] += hs[j]; pm[i] += hs[i]; pm[j] -= hs[j]; mp[i] -= hs[i]; mp[j] += hs[j]; mm[i] -= hs[i]; mm[j] -= hs[j]; Hn[i][j] = (_f(pp) - _f(pm) - _f(mp) + _f(mm)) / (4 * hs[i] * hs[j]); }
    const cov = _inv3(Hn); const se = { w: cov && cov[0][0] > 0 ? Math.sqrt(cov[0][0]) : null, a: cov && cov[1][1] > 0 ? Math.sqrt(cov[1][1]) : null, b: cov && cov[2][2] > 0 ? Math.sqrt(cov[2][2]) : null };
    const tA = se.a ? best.a / se.a : null, tB = se.b ? best.b / se.b : null; const weak = (kHi - kLo) > .25 || tA == null || tB == null || Math.abs(tA) < 2;
    let h = h0of(best.w, best.a, best.b); for (let t = 1; t < n; t++) h = best.w + best.a * r[t - 1] * r[t - 1] + best.b * h;
    return { kappa, kLo, kHi, weak, w: best.w, a: best.a, b: best.b, se, tA, tB, seedKind: SEED, annVol: Math.sqrt(h * 252), halflife: kappa < 1 ? Math.log(.5) / Math.log(kappa) : Infinity, halflifeHi: kHi < 1 ? Math.log(.5) / Math.log(kHi) : Infinity };
  }

  /* ---- OU mean-reversion fit (AR(1) on levels) ---- */
  function ouFit(x) { const n = x.length; if (n < 30) return null; const Y = x.slice(1), Xl = x.slice(0, n - 1), m = Y.length;
    const mxl = Xl.reduce((a, b) => a + b, 0) / m, myl = Y.reduce((a, b) => a + b, 0) / m; let sxx = 0, sxy = 0; for (let i = 0; i < m; i++) { sxx += (Xl[i] - mxl) * (Xl[i] - mxl); sxy += (Xl[i] - mxl) * (Y[i] - myl); }
    let phi = sxy / sxx; const c = myl - phi * mxl; let sse = 0; for (let i = 0; i < m; i++) { const e = Y[i] - (c + phi * Xl[i]); sse += e * e; }
    const s2 = sse / (m - 2), sePhi = Math.sqrt(s2 / sxx); phi = Math.min(Math.max(phi, -0.9999), 0.9999);
    const meanRev = phi < 1 && (1 - phi) > 1.96 * sePhi; const theta = (phi > 0 && phi < 1) ? -Math.log(phi) : (phi <= 0 ? Infinity : 0);
    const mu = Math.abs(1 - phi) > 1e-9 ? c / (1 - phi) : x.reduce((a, b) => a + b, 0) / n;
    const halfLife = (theta > 0 && isFinite(theta)) ? Math.log(2) / theta : Infinity;
    const sigmaX2 = Math.abs(phi) < 1 ? s2 / (1 - phi * phi) : Infinity; const last = x[n - 1];
    const z = (sigmaX2 > 0 && isFinite(sigmaX2)) ? (last - mu) / Math.sqrt(sigmaX2) : 0;
    return { phi, sePhi, theta, mu, muPrice: Math.exp(mu), halfLife, sigmaX2, meanRev, z, last }; }

  const API = { _ols, _mackinnonCV, adfTest, _nwlrv, kpssTest, ema, emaProjPath, hvRollSeries, _inv3, garch, ouFit, _lr, _vr, _sd };
  root.MrktEngine = API;                       // namespaced (used by the Node parity test)
  for (const k in API) { if (typeof root[k] === 'undefined') root[k] = API[k]; }   // bare globals for the inline dashboard code
})(typeof globalThis !== 'undefined' ? globalThis : this);
