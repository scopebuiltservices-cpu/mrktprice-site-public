/* ===== MrktPrice intraday trigger -> projection engine (Frontier Econometrics 2026 synthesis) =====
   Vanilla-JS mirror of tools/market_map/intraday_engine.py (1:1). Detects an abnormal intraday state
   via time-of-day-robust volume+RV z-gates, confirms persistence over consecutive 15-min windows with
   an econometric drift signal, integrates per-window drift in LOG-PRICE space, and wraps it in a
   trigger-matched conformal band (parametric forecast-SE fallback). NO LOOK-AHEAD: every threshold/
   quantile/SE at trigger T uses only info <= T. Exposes window.MrktIntraday.  Research only. */
(function (root) {
  'use strict';
  function median(a) {
    var s = a.filter(function (x) { return x != null && x === x; }).slice().sort(function (p, q) { return p - q; });
    var n = s.length; if (!n) return NaN; return n % 2 ? s[(n - 1) / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2]);
  }
  function mad(a, med) {
    var s = a.filter(function (x) { return x != null && x === x; }); if (!s.length) return 0;
    var m = (med == null) ? median(s) : med;
    return 1.4826 * median(s.map(function (x) { return Math.abs(x - m); }));
  }
  function z(x, m, sd) { return (sd && sd > 0) ? (x - m) / sd : 0; }

  function todNormalizers(hist) {
    var by = {};
    hist.forEach(function (b) {
      var k = b.bucket; if (!by[k]) by[k] = { lv: [], lrv: [] };
      if (b.vol > 0) by[k].lv.push(Math.log(b.vol));
      if (b.rv > 0) by[k].lrv.push(Math.log(b.rv));
    });
    var out = {};
    Object.keys(by).forEach(function (k) {
      var mV = median(by[k].lv), mRV = median(by[k].lrv);
      out[k] = { mV: mV, sV: mad(by[k].lv, mV), mRV: mRV, sRV: mad(by[k].lrv, mRV) };
    });
    return out;
  }
  function abnormality(bar, norms) {
    var nb = norms[bar.bucket]; if (!nb) return [0, 0];
    var zV = bar.vol > 0 ? z(Math.log(bar.vol), nb.mV, nb.sV) : 0;
    var zRV = bar.rv > 0 ? z(Math.log(bar.rv), nb.mRV, nb.sRV) : 0;
    return [zV, zRV];
  }
  function gateA(zV, zRV, thV, thRV) { return (zV >= thV && zRV >= thRV) ? 1 : 0; }

  function ewmaDrift(rets, lam) {
    if (!rets.length) return 0; var num = 0, den = 0, w = 1;
    for (var i = rets.length - 1; i >= 0; i--) { num += w * rets[i]; den += w; w *= lam; }
    return den ? num / den : 0;
  }
  function rollingSE(rets, mu) {
    var n = rets.length; if (n < 3) return Infinity;
    var v = 0; for (var i = 0; i < n; i++) v += (rets[i] - mu) * (rets[i] - mu);
    return Math.sqrt((v / (n - 1)) / n);
  }
  function signalQ(mu, se) { return (se && se > 0 && isFinite(se)) ? Math.abs(mu) / se : 0; }
  function highVolProb(rv, rvHist) {
    if (!rvHist.length || !rv) return 0;
    var lrv = rvHist.filter(function (x) { return x > 0; }).map(Math.log);
    var m = median(lrv), sd = mad(lrv, m);
    return 1 / (1 + Math.exp(-z(Math.log(rv), m, sd)));
  }
  function regimeGate(pHV, rho, kappa) { return pHV <= rho ? 1 : kappa; }
  function confirmM(A, q, tau, sn, sp) { return A * ((q >= tau && sn === sp && sn !== 0) ? 1 : 0); }

  function consecutiveTrigger(M, K) {
    var C = 0, T = null, path = [];
    for (var k = 0; k < M.length; k++) { C = M[k] === 1 ? C + 1 : 0; path.push(C); if (T === null && C >= K) T = k; }
    return [T, path];
  }
  function projectLogpath(pT, drifts) { var out = [], p = pT; for (var i = 0; i < drifts.length; i++) { p += drifts[i]; out.push(p); } return out; }
  function quantile(xs, qq) {
    var s = xs.slice().sort(function (a, b) { return a - b; }); if (!s.length) return 0;
    var pos = qq * (s.length - 1), lo = Math.floor(pos), hi = Math.ceil(pos);
    return lo === hi ? s[lo] : s[lo] + (s[hi] - s[lo]) * (pos - lo);
  }
  function parametricBand(lp, sig, ses, zz) {
    var lo = [], hi = [], sv = 0, se2 = 0;
    for (var h = 0; h < lp.length; h++) {
      sv += (h < sig.length ? sig[h] * sig[h] : 0); se2 += (h < ses.length ? ses[h] * ses[h] : 0);
      var fse = Math.sqrt(sv + se2); lo.push(lp[h] - zz * fse); hi.push(lp[h] + zz * fse);
    }
    return [lo, hi];
  }
  function conformalBand(lp, residByH, alpha) {
    var lo = [], hi = [], ql = (1 - alpha) / 2, qh = (1 + alpha) / 2;
    for (var h = 0; h < lp.length; h++) {
      var res = residByH[h] || residByH[h + 1] || [];
      if (res.length >= 8) { lo.push(lp[h] + quantile(res, ql)); hi.push(lp[h] + quantile(res, qh)); }
      else { lo.push(NaN); hi.push(NaN); }
    }
    return [lo, hi];
  }
  function decision(pT, hi, lo, hIdx, cost, G) {
    if (G == null) G = 1;
    if (hIdx >= hi.length) return { tradable: false, side: null, edge: 0, size: 0, regimeG: +G.toFixed(2) };
    var longS = hi[hIdx] - pT - cost, shortS = pT - lo[hIdx] - cost;
    var side = (longS > 0 && longS >= shortS) ? 'long' : (shortS > 0 ? 'short' : null);
    var edge = side === 'long' ? longS : (side === 'short' ? shortS : Math.max(longS, shortS));
    var tradable = !!(side && edge > 0 && G > 0);
    return { tradable: tradable, side: tradable ? side : null, edge: +edge.toFixed(5),
             size: tradable ? +Math.max(G, 0).toFixed(2) : 0, regimeG: +G.toFixed(2) };
  }

  function evaluate(bars, hist, params) {
    var P = { thV: 1.5, thRV: 1.5, tau: 1.5, rho: 0.5, kappa: 0.34, K: 3, H: 8, alpha: 0.90,
              cost: 0.0, lam: 0.85, warm: 6 };
    if (params) for (var kk in params) P[kk] = params[kk];
    var norms = todNormalizers(hist);
    var rvHist = hist.filter(function (b) { return b.rv > 0; }).map(function (b) { return b.rv; });
    var M = [], gates = [], signPrev = 0;
    for (var k = 0; k < bars.length; k++) {
      var b = bars[k], ab = abnormality(b, norms), A = gateA(ab[0], ab[1], P.thV, P.thRV);
      var past = []; for (var j = Math.max(0, k - 20); j <= k; j++) past.push(bars[j].ret);
      var mu = ewmaDrift(past, P.lam), se = rollingSE(past, mu), q = signalQ(mu, se);
      var rvwin = []; for (var j2 = Math.max(0, k - 3); j2 <= k; j2++) if (bars[j2].rv > 0) rvwin.push(bars[j2].rv);
      var pHV = highVolProb(rvwin.length ? median(rvwin) : b.rv, rvHist), G = regimeGate(pHV, P.rho, P.kappa);
      var sn = mu > 0 ? 1 : (mu < 0 ? -1 : 0), warm = k >= P.warm;
      var m = warm ? confirmM(A, q, P.tau, sn, signPrev) : 0; M.push(m);
      gates.push({ k: k, zV: +ab[0].toFixed(2), zRV: +ab[1].toFixed(2), A: A, q: +q.toFixed(2),
                   pHV: +pHV.toFixed(2), G: G, mu: mu, se: se, M: m });
      signPrev = sn;
    }
    var tr = consecutiveTrigger(M, P.K), T = tr[0];
    var res = { triggered: T !== null, T: T, C: tr[1], gates: gates, params: P };
    if (T === null) return res;
    var muT = gates[T].mu, seT = gates[T].se, pT = bars[T].p;
    var drifts = []; for (var h = 0; h < P.H; h++) drifts.push(muT * Math.pow(0.92, h));
    var lp = projectLogpath(pT, drifts);
    var rr = []; for (var j3 = Math.max(0, T - 20); j3 <= T; j3++) rr.push(bars[j3].ret);
    var s2 = 0; for (var i2 = 0; i2 < rr.length; i2++) s2 += (rr[i2] - muT) * (rr[i2] - muT);
    var sig1 = rr.length > 2 ? Math.sqrt(s2 / (rr.length - 1)) : Math.abs(muT) + 1e-6;
    var sig = [], ses = []; for (var h2 = 0; h2 < P.H; h2++) { sig.push(sig1); ses.push(seT); }
    var pb = parametricBand(lp, sig, ses, 1.6448536), cb = conformalBand(lp, (params && params.resid_by_h) || {}, P.alpha);
    var lo = [], hi = [], src = [];
    for (var h3 = 0; h3 < lp.length; h3++) {
      var useC = cb[0][h3] === cb[0][h3];
      lo.push(useC ? cb[0][h3] : pb[0][h3]); hi.push(useC ? cb[1][h3] : pb[1][h3]); src.push(useC ? 'conformal' : 'parametric');
    }
    res.T_bucket = bars[T].bucket; res.muT = muT; res.seT = seT;
    res.centerLog = lp; res.center = lp.map(Math.exp);
    res.loLog = lo; res.hiLog = hi; res.lo = lo.map(Math.exp); res.hi = hi.map(Math.exp);
    res.bandSource = src; res.decision = decision(pT, hi, lo, P.H - 1, P.cost, gates[T].G);
    return res;
  }

  var API = { median: median, mad: mad, todNormalizers: todNormalizers, abnormality: abnormality, gateA: gateA,
              ewmaDrift: ewmaDrift, rollingSE: rollingSE, signalQ: signalQ, highVolProb: highVolProb,
              regimeGate: regimeGate, confirmM: confirmM, consecutiveTrigger: consecutiveTrigger,
              projectLogpath: projectLogpath, parametricBand: parametricBand, conformalBand: conformalBand,
              decision: decision, evaluate: evaluate };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktIntraday = API;
})(typeof window !== 'undefined' ? window : this);
