/* lineage.js — browser-side mirror of tools/market_map/lineage.py.
   Pure, dependency-free. Same math, cross-checked to the Python decimals in test_lineage.mjs.
   Heavy fitting is server-side; these run fast on the already-computed regime/MC outputs. */
(function (root) {
  "use strict";
  var NEG_INF = -Infinity;

  // INTRADAY-WEIGHTED horizons (label, trading-days, isPrimary)
  var HORIZONS = [
    ["intraday", 0.25, true], ["1d", 1, true], ["5d", 5, true],
    ["10d", 10, false], ["20d", 20, false], ["63d", 63, false]
  ];

  function viterbi(logInit, logTrans, logLik) {
    var T = logLik.length, K = logInit.length;
    if (!T) return { path: [], logProb: 0 };
    var dp = Array.from({ length: T }, function () { return Array(K).fill(NEG_INF); });
    var back = Array.from({ length: T }, function () { return Array(K).fill(-1); });
    for (var k = 0; k < K; k++) dp[0][k] = logInit[k] + logLik[0][k];
    for (var t = 1; t < T; t++) for (k = 0; k < K; k++) {
      var best = NEG_INF, arg = -1;
      for (var j = 0; j < K; j++) { var c = dp[t - 1][j] + logTrans[j][k]; if (c > best) { best = c; arg = j; } }
      dp[t][k] = best + logLik[t][k]; back[t][k] = arg;
    }
    var last = 0; for (k = 1; k < K; k++) if (dp[T - 1][k] > dp[T - 1][last]) last = k;
    var path = Array(T).fill(0); path[T - 1] = last;
    for (t = T - 2; t >= 0; t--) path[t] = back[t + 1][path[t + 1]];
    return { path: path, logProb: dp[T - 1][last] };
  }

  function topBranches(post, trans, trajDensity, k) {
    k = k || 3; var K = post.length; trajDensity = trajDensity || post.map(function () { return 1; });
    var raw = [];
    for (var j = 0; j < K; j++) {
      var tm = (trans[j] && trans[j][j] != null) ? trans[j][j] : 1;
      raw.push(Math.max(0, post[j]) * Math.max(1e-12, tm) * Math.max(1e-12, trajDensity[j]));
    }
    var s = raw.reduce(function (a, b) { return a + b; }, 0) || 1;
    var br = raw.map(function (r, jj) { return { regime: jj, p: r / s }; });
    br.sort(function (a, b) { return b.p - a.p; });
    return br.slice(0, k);
  }

  function branchDecomposition(w, condMeans, condVars) {
    var s = w.reduce(function (a, b) { return a + b; }, 0) || 1;
    var ww = w.map(function (x) { return x / s; });
    var within = ww.reduce(function (a, _, i) { return a + ww[i] * condVars[i]; }, 0);
    var mean = ww.reduce(function (a, _, i) { return a + ww[i] * condMeans[i]; }, 0);
    var between = ww.reduce(function (a, _, i) { return a + ww[i] * Math.pow(condMeans[i] - mean, 2); }, 0);
    var total = within + between;
    if (total <= 0) return { within: 0, between: 0, total: 0, diffusive_share: 0, branching_share: 0, mean: mean };
    return { within: within, between: between, total: total,
      diffusive_share: within / total, branching_share: between / total, mean: mean };
  }

  function bridgeTouchUpper(logS0, logS1, logBarrier, varDt) {
    if (logBarrier <= Math.max(logS0, logS1)) return 1;
    if (varDt <= 0) return 0;
    return Math.max(0, Math.min(1, Math.exp(-2 * (logBarrier - logS0) * (logBarrier - logS1) / varDt)));
  }
  function bridgeTouchLower(logS0, logS1, logBarrier, varDt) {
    if (logBarrier >= Math.min(logS0, logS1)) return 1;
    if (varDt <= 0) return 0;
    return Math.max(0, Math.min(1, Math.exp(-2 * (logS0 - logBarrier) * (logS1 - logBarrier) / varDt)));
  }

  function sigmaVolumeMatrix(paths, horizons, sigmaBins) {
    var out = {};
    horizons.forEach(function (h) {
      out[h] = {};
      for (var i = 0; i < sigmaBins.length - 1; i++) {
        var lo = sigmaBins[i], hi = sigmaBins[i + 1];
        var xs = paths.filter(function (p) { return p.horizon === h && p.retZ >= lo && p.retZ < hi; })
                      .map(function (p) { return p.cumVol; });
        var mean = xs.length ? xs.reduce(function (a, b) { return a + b; }, 0) / xs.length : null;
        out[h][lo + ".." + hi] = { n: xs.length, meanCumVol: mean };
      }
    });
    return out;
  }

  function conformalPad(scores, alpha) {
    alpha = (alpha == null) ? 0.10 : alpha;
    var s = scores.slice().sort(function (a, b) { return a - b; });
    if (!s.length) return 0;
    var idx = Math.min(s.length - 1, Math.ceil((1 - alpha) * (s.length + 1)) - 1);
    return s[Math.max(0, idx)];
  }

  function hawkesExpectedCount(nowMin, eventTimesMin, muPerMin, alpha, betaPerMin, horizonMin) {
    var lam = muPerMin;
    eventTimesMin.forEach(function (tm) { var age = nowMin - tm; if (age >= 0) lam += alpha * Math.exp(-betaPerMin * age); });
    var expected = muPerMin * horizonMin;
    eventTimesMin.forEach(function (tm) {
      var age = nowMin - tm;
      if (age >= 0) expected += (alpha / betaPerMin) * Math.exp(-betaPerMin * age) * (1 - Math.exp(-betaPerMin * horizonMin));
    });
    return { lambdaNow: lam, expectedCount: expected };
  }

  function straddleLabels(s0, sigmaAnnual, tYears, straddlePrice) {
    var sig1 = s0 * sigmaAnnual * Math.sqrt(Math.max(tYears, 0));
    if (straddlePrice == null) straddlePrice = sig1 * Math.sqrt(2 / Math.PI);
    return { impliedAbsMove: straddlePrice, sigmaEquivMove: straddlePrice * Math.sqrt(Math.PI / 2), sigma1Move: sig1 };
  }

  function eventVariance(wQplus, wQminus, baseVarPerT, dtSpan) {
    return Math.max(0, wQplus - wQminus - baseVarPerT * dtSpan);
  }
  function houseBlend(sigQ2, sigP2, vEvt, omegaQ) {
    var w = Math.max(0, Math.min(1, omegaQ));
    return w * sigQ2 + (1 - w) * sigP2 + Math.max(0, vEvt);
  }

  var DRIVER_LABELS = ["associated", "event-linked", "causal"];
  function driverContributions(regimePost, betas, dfactors, names, labels) {
    var pi = regimePost.length ? regimePost.reduce(function (a, b) { return a + b; }, 0) / regimePost.length : 1;
    var raw = names.map(function (_, j) { return pi * Math.abs(betas[j]) * Math.abs(dfactors[j]); });
    var s = raw.reduce(function (a, b) { return a + b; }, 0) || 1;
    var out = names.map(function (nm, j) {
      var lab = (labels && labels[j]) || "associated";
      if (DRIVER_LABELS.indexOf(lab) < 0) lab = "associated";
      return { name: nm, contrib: raw[j] / s, sign: (betas[j] * dfactors[j] >= 0 ? 1 : -1), label: lab };
    });
    out.sort(function (a, b) { return b.contrib - a.contrib; });
    return out;
  }

  var API = {
    HORIZONS: HORIZONS, viterbi: viterbi, topBranches: topBranches,
    branchDecomposition: branchDecomposition, bridgeTouchUpper: bridgeTouchUpper,
    bridgeTouchLower: bridgeTouchLower, sigmaVolumeMatrix: sigmaVolumeMatrix,
    conformalPad: conformalPad, hawkesExpectedCount: hawkesExpectedCount,
    straddleLabels: straddleLabels, eventVariance: eventVariance, houseBlend: houseBlend,
    driverContributions: driverContributions, DRIVER_LABELS: DRIVER_LABELS
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  root.MrktLineage = API;
})(typeof self !== "undefined" ? self : this);
