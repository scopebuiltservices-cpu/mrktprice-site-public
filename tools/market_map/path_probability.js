/* path_probability.js — JS port of path_probability.py (path-dependent cone probabilities).
 *
 * Vanilla ES5-ish, no deps. Locked to the Python reference via the committed golden fixture
 * path_probability_golden.json (Python is authoritative); test_path_probability_parity.mjs checks
 * JS == Py to 1e-6. All quantities are in LOG-RETURN space: barrier b = ln(B/S0), scale s = sigmaDaily
 * * sqrt(T), drift m = muDaily * T. Lets the terminal show the exact closed-form touch odds, MFE/MAE and
 * P(end>=level | touched barrier) live, and cross-check its Monte-Carlo cone.
 */
(function (root, factory) {
  var mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else root.PathProb = mod;
})(typeof self !== 'undefined' ? self : this, function () {
  var SQRT2 = Math.sqrt(2.0), SQRT_2_OVER_PI = Math.sqrt(2.0 / Math.PI);

  function erf(x) { // Abramowitz-Stegun 7.1.26 (|err|<1.5e-7)
    var s = x < 0 ? -1 : 1; x = Math.abs(x);
    var t = 1.0 / (1.0 + 0.3275911 * x);
    var y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return s * y;
  }
  function ncdf(x) { return 0.5 * (1.0 + erf(x / SQRT2)); }
  function nppf(p) { // Acklam inverse-normal
    if (p <= 0) return -Infinity; if (p >= 1) return Infinity;
    var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
    var b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
    var c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
    var d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];
    var plow = 0.02425, phigh = 1 - plow, q, r;
    if (p < plow) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (p > phigh) { q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }

  function priceToReturn(price, s0) { return Math.log(price / s0); }
  function returnToPrice(r, s0) { return s0 * Math.exp(r); }

  function touchUp(b, s, m) {
    m = m || 0.0;
    if (s <= 0) return b <= 0 ? 1.0 : 0.0;
    if (b <= 0) return 1.0;
    return Math.min(1.0, ncdf((m - b) / s) + Math.exp(2.0 * m * b / (s * s)) * ncdf((-b - m) / s));
  }
  function touchDown(b, s, m) { return touchUp(-b, s, -(m || 0.0)); }
  function runningMaxCdfGe(b, s, m) { return b > 0 ? touchUp(b, s, m) : 1.0; }

  function runningMaxQuantile(p, s, m) {
    m = m || 0.0;
    if (s <= 0) return Math.max(0.0, m);
    if (Math.abs(m) < 1e-15) return s * nppf((1.0 + p) / 2.0);
    var lo = 0.0, hi = m + 12.0 * s, mid, i;
    for (i = 0; i < 80; i++) { mid = 0.5 * (lo + hi); if ((1.0 - runningMaxCdfGe(mid, s, m)) < p) lo = mid; else hi = mid; }
    return 0.5 * (lo + hi);
  }

  function expectedMaxFavorable(s, m) {
    m = m || 0.0;
    if (s <= 0) return Math.max(0.0, m);
    if (Math.abs(m) < 1e-15) return s * SQRT_2_OVER_PI;
    var hi = Math.max(0.0, m) + 12.0 * s, n = 2000, h = hi / n, i;
    var tot = runningMaxCdfGe(0.0, s, m) + runningMaxCdfGe(hi, s, m);
    for (i = 1; i < n; i++) tot += (i % 2 ? 4 : 2) * runningMaxCdfGe(i * h, s, m);
    return tot * h / 3.0;
  }
  function expectedMaxAdverse(s, m) { return expectedMaxFavorable(s, -(m || 0.0)); }

  function probEndAboveGivenTouchUp(b, k, s, m) {
    m = m || 0.0;
    if (s <= 0) return (m >= b && m >= k) ? 1.0 : 0.0;
    var denom = touchUp(b, s, m);
    if (denom <= 0) return 0.0;
    // exact reflection for m==0 (the terminal path_report uses driftless)
    var joint = (k <= b) ? (2.0 * ncdf(-b / s) - ncdf(-(2.0 * b - k) / s)) : ncdf(-k / s);
    return Math.max(0.0, Math.min(1.0, joint / denom));
  }

  function _r(x, n) { var p = Math.pow(10, n); return Math.round(x * p) / p; }  // match Python round()
  function pathReport(s0, sigmaDaily, T, barrierUp, barrierDn, level, driftDaily) {
    var s = sigmaDaily * Math.sqrt(T), m = (driftDaily || 0.0) * T;
    // rounding mirrors path_probability.py's path_report exactly (ret 6dp, price 4dp, prob 4dp) so the
    // committed golden fixture matches to floating precision.
    var out = { T: T, s: _r(s, 6), m: _r(m, 6), mfeRet: _r(expectedMaxFavorable(s, m), 6), maeRet: _r(expectedMaxAdverse(s, m), 6) };
    out.mfePrice = _r(returnToPrice(out.mfeRet, s0), 4);
    out.maePrice = _r(returnToPrice(-out.maeRet, s0), 4);
    if (barrierUp != null && barrierUp > s0) out.touchUp = _r(touchUp(priceToReturn(barrierUp, s0), s, m), 4);
    if (barrierDn != null && barrierDn > 0 && barrierDn < s0) out.touchDn = _r(touchDown(priceToReturn(barrierDn, s0), s, m), 4);
    if (barrierUp != null && level != null && barrierUp > s0)
      out.pEndAboveGivenTouchUp = _r(probEndAboveGivenTouchUp(priceToReturn(barrierUp, s0), priceToReturn(level, s0), s, m), 4);
    return out;
  }

  return {
    ncdf: ncdf, nppf: nppf, priceToReturn: priceToReturn, returnToPrice: returnToPrice,
    touchUp: touchUp, touchDown: touchDown, runningMaxQuantile: runningMaxQuantile,
    expectedMaxFavorable: expectedMaxFavorable, expectedMaxAdverse: expectedMaxAdverse,
    probEndAboveGivenTouchUp: probEndAboveGivenTouchUp, pathReport: pathReport
  };
});
