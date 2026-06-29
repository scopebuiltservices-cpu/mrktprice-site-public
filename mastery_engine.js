/* mastery_engine.js — 1:1 JS port of mastery_engine.py. Evidence-based signal-mastery gate
   (novice/proficient/mastery, critical-component override, two-confirmation, IRT-style confidence bands).
   exports window.MrktMastery / module.exports. Research only, not advice. */
(function (root, factory) {
  var m = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = m;
  if (typeof window !== 'undefined') window.MrktMastery = m;
})(this, function () {
  'use strict';
  var DEFAULT_WEIGHTS = { concepts: 0.20, procedure: 0.25, reasoning: 0.20, transfer: 0.25, selfmon: 0.10 };
  function clamp01(x) { return Math.max(0, Math.min(1, x)); }

  function composite(components, weights) {
    var w = weights || DEFAULT_WEIGHTS;
    var keys = Object.keys(w).filter(function (k) { return components[k] != null; });
    if (!keys.length) return 0;
    var tw = 0; keys.forEach(function (k) { tw += w[k]; });
    if (tw <= 0) return 0;
    var s = 0; keys.forEach(function (k) { s += (w[k] / tw) * clamp01(components[k]); });
    return 100 * s;
  }
  function confidenceBand(n, se, nStrong, nModerate) {
    if (nStrong == null) nStrong = 500; if (nModerate == null) nModerate = 120;
    if (n == null || n < 30) return 'insufficient';
    var wide = (se != null && se > 0.15);
    if (n >= nStrong && !wide) return 'strong';
    if (n >= nModerate) return wide ? 'insufficient' : 'moderate';
    return n >= 60 ? 'moderate' : 'insufficient';
  }
  function twoConfirmation(a, b) { return !!a && !!b; }
  function classify(components, criticals, opt) {
    opt = opt || {};
    var weights = opt.weights, ce = !!opt.criticalError, nM = opt.nMisconceptions || 0, maxM = opt.maxMiscon == null ? 2 : opt.maxMiscon;
    var ip = opt.initialPass == null ? true : opt.initialPass, dp = opt.delayedPass == null ? true : opt.delayedPass;
    var n = opt.n, se = opt.se;
    var cfp = opt.critFloorProf == null ? 60 : opt.critFloorProf, cfm = opt.critFloorMast == null ? 80 : opt.critFloorMast;
    var po = opt.profOverall == null ? 70 : opt.profOverall, mo = opt.mastOverall == null ? 85 : opt.mastOverall;
    var crit = criticals || {};
    var overall = composite(components, weights);
    var crit100 = {}, minCrit = 100, blocked = [];
    Object.keys(crit).forEach(function (k) { crit100[k] = 100 * clamp01(crit[k]); minCrit = Math.min(minCrit, crit100[k]); });
    if (ce) blocked.push('critical_error');
    Object.keys(crit100).forEach(function (k) { if (crit100[k] < cfp) blocked.push('critical:' + k + '<' + cfp); });
    var tier;
    if (overall < po || minCrit < cfp || nM > maxM) tier = 'novice';
    else if (overall >= mo && minCrit >= cfm && !ce && twoConfirmation(ip, dp)) tier = 'mastery';
    else tier = 'proficient';
    var why = [];
    if (tier !== 'mastery') {
      if (overall < mo) why.push('overall ' + Math.round(overall) + '<85');
      if (minCrit < cfm) why.push('a critical<80');
      if (ce) why.push('critical error');
      if (!twoConfirmation(ip, dp)) why.push('needs delayed re-confirm');
    }
    return { tier: tier, overall: Math.round(overall * 10) / 10, minCritical: Math.round(minCrit * 10) / 10,
      band: confidenceBand(n, se), blockedBy: blocked, whyNotMastery: why, deployable: tier === 'mastery' };
  }
  function reclassify(history, maintain) {
    if (maintain == null) maintain = 80;
    if (history.length < 2) return false;
    return history[history.length - 1] < maintain && history[history.length - 2] < maintain;
  }
  return { composite: composite, confidenceBand: confidenceBand, twoConfirmation: twoConfirmation,
    classify: classify, reclassify: reclassify, DEFAULT_WEIGHTS: DEFAULT_WEIGHTS };
});
