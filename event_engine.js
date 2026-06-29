/* event_engine.js — 1:1 JS port of event_engine.py. Event-study math for SEC filings (8-K/13D/13G/3-4-5).
   exports window.MrktEvent / module.exports. Research only, not advice. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktEvent = m;
})(this, function () {
  'use strict';
  var EIGHTK_SEVERITY = {
    "1.01": 0.55, "1.02": 0.55, "1.03": 0.95,
    "2.01": 0.70, "2.02": 0.60, "2.03": 0.45, "2.04": 0.60, "2.05": 0.55, "2.06": 0.80,
    "3.01": 0.65, "3.02": 0.40, "3.03": 0.45,
    "4.01": 0.85, "4.02": 0.95,
    "5.01": 0.70, "5.02": 0.55, "5.03": 0.30, "5.07": 0.25,
    "7.01": 0.30, "8.01": 0.25
  };
  function eightkSeverity(items) {
    var best = 0.0, i;
    if (items) for (i = 0; i < items.length; i++) { var s = EIGHTK_SEVERITY[String(items[i]).trim()]; best = Math.max(best, s == null ? 0.25 : s); }
    return best;
  }
  function ols2(x, y) {
    var n = x.length, i;
    if (n < 2) return [n ? y.reduce(function (a, b) { return a + b; }, 0) / n : 0, 0];
    var mx = 0, my = 0; for (i = 0; i < n; i++) { mx += x[i]; my += y[i]; } mx /= n; my /= n;
    var sxx = 0, sxy = 0; for (i = 0; i < n; i++) { sxx += (x[i] - mx) * (x[i] - mx); sxy += (x[i] - mx) * (y[i] - my); }
    var b = sxx > 0 ? sxy / sxx : 0; return [my - b * mx, b];
  }
  function abnormalReturns(ri, rm, estLo, estHi, evLo, evHi) {
    var xe = rm.slice(estLo, estHi), ye = ri.slice(estLo, estHi), ab = ols2(xe, ye), a = ab[0], b = ab[1], i;
    var resid = []; for (i = 0; i < ye.length; i++) resid.push(ye[i] - (a + b * xe[i]));
    var n = resid.length, sigma = 0;
    if (n > 2) { var m = resid.reduce(function (p, q) { return p + q; }, 0) / n, ss = 0; for (i = 0; i < n; i++) ss += (resid[i] - m) * (resid[i] - m); sigma = Math.sqrt(ss / (n - 2)); }
    var ar = []; for (i = evLo; i <= evHi; i++) ar.push(ri[i] - (a + b * rm[i]));
    return { ar: ar, sigma: sigma, a: a, b: b };
  }
  function car(ar) { return ar.reduce(function (a, b) { return a + b; }, 0); }
  function scar(ar, sigma) { var n = ar.length; if (!n || sigma <= 0) return 0; return car(ar) / (sigma * Math.sqrt(n)); }
  function eventIntensity(events, tNow, tau) {
    if (tau == null) tau = 10.0; var I = 0, i;
    for (i = 0; i < events.length; i++) { var te = events[i][0], s = events[i][1]; if (te <= tNow) I += s * Math.exp(-(tNow - te) / tau); }
    return I;
  }
  function stakeSignal(form, dpct, isNew, sign) {
    if (sign == null) sign = 1;
    var g = String(form).toUpperCase().indexOf("13D") === 0 ? 1.0 : 0.45;
    var raw = sign * (g * (dpct / 5.0) + (isNew ? 0.4 : 0.0) * g);
    return Math.max(-1.0, Math.min(1.0, raw));
  }
  function insiderNet(buyVal, discSell, planSell, rho) {
    if (rho == null) rho = 0.35; var wSell = discSell + rho * planSell;
    return (buyVal - wSell) / (buyVal + wSell + 1e-9);
  }
  function eventTilt(carVal, intensity, stake, netins, k1, k2, th, cap) {
    if (k1 == null) k1 = 0.05; if (k2 == null) k2 = 2.0; if (cap == null) cap = 3.0;
    th = th || [0.6, 0.4, 0.5, 0.5];
    var val = th[0] * Math.tanh(carVal / k1) + th[1] * Math.tanh(intensity / k2) + th[2] * stake + th[3] * netins;
    return Math.max(-cap, Math.min(cap, val));
  }
  return { EIGHTK_SEVERITY: EIGHTK_SEVERITY, eightkSeverity: eightkSeverity, ols2: ols2,
    abnormalReturns: abnormalReturns, car: car, scar: scar, eventIntensity: eventIntensity,
    stakeSignal: stakeSignal, insiderNet: insiderNet, eventTilt: eventTilt };
});
