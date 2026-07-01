/* kolmogorov_gate.js — JS port of kolmogorov_gate.py (KS advanced dual gate).
 * Lets the terminal compute the stationarity gate LIVE from the on-screen returns and toggle it on/off.
 * Locked to the Python reference via kolmogorov_gate_golden.json (test_kolmogorov_gate_parity.mjs). */
(function (root, factory) {
  var mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else root.KGate = mod;
})(typeof self !== 'undefined' ? self : this, function () {

  function ecdfAt(sorted, x) { // fraction <= x, binary search
    var lo = 0, hi = sorted.length, mid;
    while (lo < hi) { mid = (lo + hi) >> 1; if (sorted[mid] <= x) lo = mid + 1; else hi = mid; }
    return lo / sorted.length;
  }

  function probks(alam) {
    if (alam <= 0) return 1.0;
    var a2 = -2.0 * alam * alam, fac = 2.0, s = 0.0, termbf = 0.0, j, term;
    for (j = 1; j <= 100; j++) {
      term = fac * Math.exp(a2 * j * j); s += term;
      if (Math.abs(term) <= 1e-3 * termbf || Math.abs(term) <= 1e-8 * s) return Math.max(0.0, Math.min(1.0, s));
      fac = -fac; termbf = Math.abs(term);
    }
    return 1.0;
  }

  function ksTwoSample(a, b) {
    a = a.filter(function (x) { return x === x; }).map(Number).sort(function (p, q) { return p - q; });
    b = b.filter(function (x) { return x === x; }).map(Number).sort(function (p, q) { return p - q; });
    var na = a.length, nb = b.length, i, D = 0.0;
    if (na === 0 || nb === 0) return { D: 0.0, p: 1.0, ne: 0 };
    for (i = 0; i < na; i++) D = Math.max(D, Math.abs(ecdfAt(a, a[i]) - ecdfAt(b, a[i])));
    for (i = 0; i < nb; i++) D = Math.max(D, Math.abs(ecdfAt(a, b[i]) - ecdfAt(b, b[i])));
    var ne = na * nb / (na + nb), sn = Math.sqrt(ne);
    var lam = (sn + 0.12 + 0.11 / sn) * D;
    return { D: D, p: probks(lam), ne: ne };
  }

  function r4(x) { return Math.round(x * 1e4) / 1e4; }
  function r1(x) { return Math.round(x * 10) / 10; }

  function dualGate(returns, refWindow, curWindow, alpha, minN) {
    refWindow = refWindow || 120; curWindow = curWindow || 60; alpha = (alpha == null ? 0.05 : alpha); minN = minN || 30;
    var r = returns.filter(function (x) { return x === x; }).map(Number), n = r.length;
    var cur = n >= curWindow ? r.slice(n - curWindow) : r.slice();
    var ref = n >= curWindow + refWindow ? r.slice(n - curWindow - refWindow, n - curWindow) : (cur.length < n ? r.slice(0, n - cur.length) : []);
    var nref = ref.length, ncur = cur.length;
    var sufficient = (nref >= minN && ncur >= minN);
    var ks = sufficient ? ksTwoSample(ref, cur) : { D: 0.0, p: 1.0, ne: 0.0 };
    var stationary = sufficient && (ks.p >= alpha);
    var passed = !!(sufficient && stationary);
    var reason = !sufficient ? ('insufficient history (need ' + minN + ' each; ref=' + nref + ' cur=' + ncur + ')')
      : (!stationary ? ('regime shift: current return law differs from reference (KS p=' + ks.p.toFixed(3) + ' < ' + alpha + ')')
        : ('stationary vs reference (KS p=' + ks.p.toFixed(3) + ')'));
    var suffRamp = sufficient ? Math.max(0.0, Math.min(1.0, (Math.min(nref, ncur) - minN) / Math.max(1, minN))) : 0.0;
    var grade = r4((stationary ? ks.p : 0.0) * (0.5 + 0.5 * suffRamp));
    return {
      passed: passed, sufficient: !!sufficient, stationary: !!stationary,
      ksD: r4(ks.D), ksP: r4(ks.p), nRef: nref, nCur: ncur, nEff: r1(ks.ne), alpha: alpha,
      grade: grade, reason: reason, status: passed ? 'admissible' : (sufficient ? 'regime-shifted' : 'thin')
    };
  }

  return { ksTwoSample: ksTwoSample, probks: probks, dualGate: dualGate };
});
