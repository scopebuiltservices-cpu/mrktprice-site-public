/* volatility_arbiter.js — browser twin of volatility_arbiter.py (reliability-weighted variance blend).
 * Lets the terminal compute one horizon sigma_H from physical vol components + a VR overlay + additive
 * event/jump variance, LIVE. Locked to the Python reference via va_golden.json (test_volatility_arbiter_parity.mjs). */
(function (root, factory) {
  var mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else root.VolArbiter = mod;
})(typeof self !== 'undefined' ? self : this, function () {

  var VERSION = 'vol_arbiter_v1';

  function component(name, sigma, reliability, base_weight, available) {
    return {
      name: String(name), sigma: +sigma, reliability: +reliability,
      base_weight: (base_weight == null ? 1.0 : +base_weight),
      available: (available == null ? true : !!available)
    };
  }

  function clip(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
  function r6(x) { return Math.round(x * 1e6) / 1e6; }

  function vrLambda(vr, nEff, minN, kmax) {
    minN = (minN == null ? 60 : minN); kmax = (kmax == null ? 0.5 : kmax);
    if (vr == null || nEff == null || nEff < minN) return 0.0;
    var samp = clip((nEff - minN) / (3.0 * minN), 0.0, 1.0);
    var dep = clip(Math.abs(vr - 1.0) / 0.5, 0.0, 1.0);
    return r6(kmax * samp * dep);
  }

  function blend(physical, opt) {
    opt = opt || {};
    var sigma_vr = (opt.sigma_vr == null ? null : +opt.sigma_vr);
    var vr_reliability = opt.vr_reliability || 0.0;
    var event_sigma = opt.event_sigma || 0.0, jump_sigma = opt.jump_sigma || 0.0;
    var floor = (opt.floor == null ? 1e-6 : opt.floor), cap = (opt.cap == null ? 10.0 : opt.cap);

    var usable = physical.filter(function (c) { return (c.available !== false) && (+c.sigma > 0); });
    if (!usable.length) throw new Error('no usable physical volatility components');

    var raw = usable.map(function (c) {
      return Math.max(c.base_weight == null ? 1.0 : c.base_weight, 0.0) * clip(c.reliability || 0.0, 0.0, 1.0);
    });
    var tot = raw.reduce(function (a, b) { return a + b; }, 0.0);
    if (tot <= 0.0) { raw = usable.map(function () { return 1.0; }); tot = usable.length; }
    var weights = raw.map(function (r) { return r / tot; });

    var sigma2 = 0.0, i, s;
    for (i = 0; i < usable.length; i++) { s = Math.max(usable[i].sigma, 1e-12); sigma2 += weights[i] * s * s; }
    var out_weights = {};
    for (i = 0; i < usable.length; i++) out_weights[usable[i].name] = r6(weights[i]);

    if (sigma_vr != null && vr_reliability > 0.0) {
      var lam = clip(+vr_reliability, 0.0, 1.0);
      var sv = Math.max(sigma_vr, floor);
      sigma2 = (1.0 - lam) * sigma2 + lam * sv * sv;
      out_weights['vr_overlay'] = r6(lam);
    }

    var ev = Math.max(+event_sigma, 0.0), jp = Math.max(+jump_sigma, 0.0);
    var sigma2_total = sigma2 + ev * ev + jp * jp;
    var sigma = Math.min(Math.max(Math.sqrt(sigma2_total), floor), cap);

    var mean_rel = 0.0;
    for (i = 0; i < usable.length; i++) mean_rel += weights[i] * (usable[i].reliability || 0.0);
    var comps = {};
    for (i = 0; i < usable.length; i++) comps[usable[i].name] = usable[i].sigma;
    comps.event_sigma = ev; comps.jump_sigma = jp;

    return {
      sigma: sigma, sigma2: sigma2_total, weights: out_weights,
      reliability: r6(mean_rel), components: comps, version: VERSION
    };
  }

  return { component: component, blend: blend, vrLambda: vrLambda, VERSION: VERSION };
});
