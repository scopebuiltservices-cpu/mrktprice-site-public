/* fib_engine.js — 1:1 JS port of tools/market_map/fib_ref.py (multi-horizon projection, Phase 1-2).
   Powers the projClose-vs-priceNow horizon tiles (fib_panel.js). Verified-engine pattern: the Python
   reference is authoritative; this port is locked to tools/fib_golden.json by tools/test_fib_parity.mjs.
   Reuses the canonical metrics math (variance-ratio horizon vol, OU half-life decay, blended EWMA sigma).
   Exposes window.MrktFib (UMD). Pure, no deps. */
(function (root) {
  'use strict';

  // ---- Python round (round-half-to-even) so rounded half_life/variance_ratio match the reference ----
  function pyRound(x, n) {
    if (!isFinite(x)) return x;
    var m = Math.pow(10, n), v = x * m, fl = Math.floor(v), diff = v - fl, r;
    if (diff > 0.5) r = fl + 1;
    else if (diff < 0.5) r = fl;
    else r = (fl % 2 === 0) ? fl : fl + 1;   // exact tie -> even
    return r / m;
  }

  // ---- canonical metrics primitives (ported from metrics.py) ----
  function _clean(xs) { var o = []; for (var i = 0; i < xs.length; i++) { var x = xs[i]; if (x != null && x === x) o.push(+x); } return o; }
  function _ok() { for (var i = 0; i < arguments.length; i++) { var x = arguments[i]; if (x == null || x !== x) return false; } return true; }

  function _logret(closes, n) {
    var r = [];
    for (var i = 1; i < closes.length; i++) {
      var a = closes[i], b = closes[i - 1];
      if (_ok(a, b) && a > 0 && b > 0) r.push(Math.log(a / b));
    }
    return (n != null && n) ? r.slice(-n) : r;
  }
  function stdev(xs, ddof) {
    ddof = (ddof == null ? 1 : ddof);
    var v = _clean(xs);
    if (v.length <= ddof) return NaN;
    var m = 0, i; for (i = 0; i < v.length; i++) m += v[i]; m /= v.length;
    var s = 0; for (i = 0; i < v.length; i++) { var d = v[i] - m; s += d * d; }
    return Math.sqrt(s / (v.length - ddof));
  }
  function _var(a) {
    var v = []; for (var i = 0; i < a.length; i++) if (a[i] === a[i]) v.push(a[i]);
    if (v.length < 2) return 0.0;
    var m = 0, j; for (j = 0; j < v.length; j++) m += v[j]; m /= v.length;
    var s = 0; for (j = 0; j < v.length; j++) { var d = v[j] - m; s += d * d; }
    return s / (v.length - 1);
  }
  function beta(a, m) {
    var pr = []; for (var i = 0; i < Math.min(a.length, m.length); i++) if (a[i] === a[i] && m[i] === m[i]) pr.push([a[i], m[i]]);
    var n = pr.length; if (n < 5) return NaN;
    var ma = 0, mm = 0, k; for (k = 0; k < n; k++) { ma += pr[k][0]; mm += pr[k][1]; } ma /= n; mm /= n;
    var cov = 0, vv = 0; for (k = 0; k < n; k++) { cov += (pr[k][0] - ma) * (pr[k][1] - mm); vv += (pr[k][1] - mm) * (pr[k][1] - mm); }
    cov /= (n - 1); vv /= (n - 1);
    return vv > 0 ? cov / vv : NaN;
  }
  function half_life(closes, cap) {
    cap = (cap == null ? 252 : cap);
    var p = []; for (var i = 0; i < closes.length; i++) { var c = closes[i]; if (_ok(c) && c > 0) p.push(Math.log(c)); }
    if (p.length < 25) return null;
    var dp = [], lag = []; for (var j = 1; j < p.length; j++) { dp.push(p[j] - p[j - 1]); lag.push(p[j - 1]); }
    var b = beta(dp, lag);
    if (b !== b || b >= 0) return null;
    var h = Math.log(2) / (-b);
    return h > 0 ? pyRound(Math.min(h, cap), 1) : null;
  }
  function variance_ratio(closes, q) {
    q = (q == null ? 5 : q);
    var r = _logret(closes);
    if (r.length < q * 4) return null;
    var v1 = _var(r);
    if (v1 <= 0) return null;
    var qs = []; for (var i = 0; i <= r.length - q; i++) { var s = 0; for (var k = 0; k < q; k++) s += r[i + k]; qs.push(s); }
    var vq = _var(qs);
    return v1 > 0 ? pyRound(vq / (q * v1), 2) : null;
  }
  function ewma_vol(returns, lam, annualize) {
    lam = (lam == null ? 0.94 : lam); annualize = (annualize == null ? 252 : annualize);
    var v = _clean(returns);
    if (!v.length) return NaN;
    var vr = v[0] * v[0];
    for (var i = 1; i < v.length; i++) vr = lam * vr + (1 - lam) * v[i] * v[i];
    var s = Math.sqrt(vr);
    return annualize ? s * Math.sqrt(annualize) : s;
  }

  // ---- fib_ref.py projection layer ----
  var PRESETS = { cadence: [1, 5, 10, 21, 63], fib: [1, 2, 3, 5, 8, 13, 21, 34, 55], powers: [1, 2, 4, 8, 16] };
  var USER_TILES = { '24H': 1, '48H': 2, '1W': 5, '1M': 21 };
  function horizons(preset) { return (PRESETS[preset] || PRESETS.cadence).slice(); }

  function fit_halflife(closes, fallback) {
    fallback = (fallback == null ? 3.0 : fallback);
    var hl = half_life(closes);
    return (hl != null && hl > 0) ? hl : fallback;
  }
  function retention(hl) { return (hl && hl > 0) ? Math.pow(0.5, 1.0 / hl) : 0.0; }
  function decayed_edge(edge, hl, H) {
    var r = retention(hl);
    if (H <= 0) return 0.0;
    if (Math.abs(1.0 - r) < 1e-12) return edge * H;
    return edge * (1.0 - Math.pow(r, H)) / (1.0 - r);
  }
  function blended_sigma_daily(rets, window, lam, w_ewma) {
    window = (window == null ? 20 : window); lam = (lam == null ? 0.94 : lam); w_ewma = (w_ewma == null ? 0.5 : w_ewma);
    var v = rets.length >= window ? rets.slice(-window) : rets;
    var simple = stdev(v);
    var ew = ewma_vol(rets, lam, 0);
    if (simple !== simple) simple = ew;
    if (ew !== ew) ew = simple;
    if (simple !== simple && ew !== ew) return NaN;
    return w_ewma * ew + (1.0 - w_ewma) * simple;
  }
  function horizon_sigma(closes, H, sigma_d) {
    if (H <= 1) return sigma_d;
    var vr = variance_ratio(closes, H);
    if (vr == null || vr <= 0) vr = 1.0;
    return sigma_d * Math.sqrt(H * vr);
  }
  function sigma_total(sp, sm, se) {
    var s = sp * sp;
    if (sm) s += sm * sm;
    if (se) s += se * se;
    return Math.sqrt(s);
  }
  function _normCdf(x) { return 0.5 * (1.0 + erf(x / Math.sqrt(2.0))); }
  function erf(x) {  // Abramowitz-Stegun 7.1.26 (matches math.erf to ~1e-7; tiles use it for P(up))
    var s = x < 0 ? -1 : 1; x = Math.abs(x);
    var t = 1.0 / (1.0 + 0.3275911 * x);
    var y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return s * y;
  }
  function prob_above(price_now, mu_H, sigma_H, K) {
    if (sigma_H == null || sigma_H <= 0) return NaN;
    return 1.0 - _normCdf((Math.log(K / price_now) - mu_H) / sigma_H);
  }

  function project(price_now, edge, closes, horizon_list, opt) {
    opt = opt || {};
    var hl = (opt.hl != null) ? opt.hl : null;
    var z = (opt.z != null) ? opt.z : 1.0;
    var cap_mult = (opt.cap_mult != null) ? opt.cap_mult : 2.0;
    var cap_daily = (opt.cap_daily != null) ? opt.cap_daily : null;
    if (!(price_now > 0)) throw new Error('price_now must be > 0');
    var rets = _logret(closes);
    var sigma_d = blended_sigma_daily(rets);
    if (hl == null) hl = fit_halflife(closes);
    var e = edge;
    if (cap_daily != null && sigma_d === sigma_d) e = Math.max(-cap_daily * sigma_d, Math.min(cap_daily * sigma_d, e));
    var p0 = Math.log(price_now), out = [];
    for (var i = 0; i < horizon_list.length; i++) {
      var H = horizon_list[i];
      var sH_proc = horizon_sigma(closes, H, sigma_d);
      var sH = sigma_total(sH_proc);
      var mu = decayed_edge(e, hl, H);
      var cap = cap_mult * sH_proc;
      var capped = (cap === cap) && Math.abs(mu) > cap;
      var mu_c = (cap === cap) ? Math.max(-cap, Math.min(cap, mu)) : mu;
      var proj_log = p0 + mu_c;
      var zedge = (sH && sH > 0) ? (mu_c / sH) : NaN;
      var lo = Math.exp(proj_log - z * sH), hi = Math.exp(proj_log + z * sH);
      out.push({ H: H, projLog: proj_log, projPrice: Math.exp(proj_log), muLog: mu_c, sigmaH: sH,
        zEdge: zedge, capped: !!capped, source: 'fallback', lo: lo, hi: hi, bandMethod: 'parametric' });
    }
    return out;
  }

  function user_subset(projections) {
    var byH = {}; projections.forEach(function (p) { byH[p.H] = p; });
    var out = {}; Object.keys(USER_TILES).forEach(function (lab) { var H = USER_TILES[lab]; if (byH[H]) out[lab] = byH[H]; });
    return out;
  }

  function score(price_now, proj_log, sigma_H, realized_close) {
    var p0 = Math.log(price_now), ry = Math.log(realized_close);
    var log_err = ry - proj_log, rw_err = ry - p0;
    var proj_move = proj_log - p0, real_move = ry - p0;
    return {
      dollarErr: realized_close - Math.exp(proj_log),
      pctErr: Math.exp(ry - proj_log) - 1.0,
      logErr: log_err,
      zErr: (sigma_H && sigma_H > 0) ? log_err / sigma_H : NaN,
      dirHit: ((proj_move === 0 && real_move === 0) || (proj_move * real_move > 0)) ? 1 : 0,
      magRatio: Math.abs(proj_move) > 1e-12 ? real_move / proj_move : NaN,
      skillVsRW: Math.abs(rw_err) > 1e-12 ? 1.0 - Math.abs(log_err) / Math.abs(rw_err) : NaN
    };
  }

  var API = {
    PRESETS: PRESETS, USER_TILES: USER_TILES, horizons: horizons,
    half_life: half_life, variance_ratio: variance_ratio, ewma_vol: ewma_vol, stdev: stdev, logret: _logret,
    fit_halflife: fit_halflife, retention: retention, decayed_edge: decayed_edge,
    blended_sigma_daily: blended_sigma_daily, horizon_sigma: horizon_sigma, sigma_total: sigma_total,
    project: project, prob_above: prob_above, user_subset: user_subset, score: score
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktFib = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
