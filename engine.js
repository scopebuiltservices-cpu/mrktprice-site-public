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

  const API = { _ols, _mackinnonCV, adfTest, _nwlrv, kpssTest };
  root.MrktEngine = API;                       // namespaced (used by the Node parity test)
  for (const k in API) { if (typeof root[k] === 'undefined') root[k] = API[k]; }   // bare globals for the inline dashboard code
})(typeof globalThis !== 'undefined' ? globalThis : this);
