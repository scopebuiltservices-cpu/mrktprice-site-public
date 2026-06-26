/* ===== MrktPrice intraday 15-min -> END-OF-DAY analytics (1:1 mirror of tools/market_map/intraday_eod.py)
   Projects EOD close / total volume / day-% from the live 15-min stream + daily history. No look-ahead.
   Exposes window.MrktIntradayEOD. Research only. */
(function (root) {
  'use strict';
  var BPD = 26, ANN = 252;
  function mean(a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; }

  function intradayRV(returns) {
    var rs = returns.filter(function (r) { return r != null && r === r; });
    if (!rs.length) return { rvDay: 0, rvAnn: 0, n: 0 };
    var ss = rs.reduce(function (a, r) { return a + r * r; }, 0);
    var perBucket = Math.sqrt(ss / rs.length);
    var rvFull = perBucket * Math.sqrt(BPD);
    return { rvDay: rvFull, rvSoFar: Math.sqrt(ss), rvAnn: rvFull * Math.sqrt(ANN), n: rs.length };
  }
  function todVolumeProfile(n) {
    n = n || BPD; var w = [];
    for (var i = 0; i < n; i++) { var edge = Math.exp(-i / 4) + Math.exp(-(n - 1 - i) / 4); w.push(1 + 2.6 * edge); }
    var s = w.reduce(function (a, b) { return a + b; }, 0); return w.map(function (x) { return x / s; });
  }
  function volumePace(cumVol, elapsed, total, avgDailyVol, profile) {
    total = total || BPD; var prof = profile || todVolumeProfile(total);
    elapsed = Math.max(0, Math.min(elapsed, prof.length));
    var frac = prof.slice(0, elapsed).reduce(function (a, b) { return a + b; }, 0) || 1e-9;
    var proj = cumVol / frac, pace = null;
    if (avgDailyVol && avgDailyVol > 0) pace = cumVol / (avgDailyVol * frac);
    return { projEodVol: proj, fracDone: frac, pace: pace };
  }
  function eodCloseProjection(pNowLog, driftPerBucket, sigmaPerBucket, bucketsRemaining, openPx, z) {
    if (z == null) z = 1.6448536; var rem = Math.max(0, bucketsRemaining);
    var pClose = pNowLog + driftPerBucket * rem, band = rem > 0 ? z * sigmaPerBucket * Math.sqrt(rem) : 0;
    var close = Math.exp(pClose), lo = Math.exp(pClose - band), hi = Math.exp(pClose + band), o = { close: close, lo: lo, hi: hi };
    if (openPx && openPx > 0) { o.pctClose = close / openPx - 1; o.pctLo = lo / openPx - 1; o.pctHi = hi / openPx - 1; }
    return o;
  }
  function eodOutlook(bars, ctx) {
    bars = (bars || []).filter(Boolean); if (!bars.length) return null; ctx = ctx || {};
    var total = ctx.totalBuckets || BPD, elapsed = bars.length, rem = Math.max(0, total - elapsed);
    var rets = bars.map(function (b) { return b.ret || 0; }), vols = bars.map(function (b) { return b.vol || 0; });
    var prices = bars.map(function (b) { return b.price; }).filter(function (p) { return p; });
    var cumVol = vols.reduce(function (a, b) { return a + b; }, 0);
    var priceNow = prices.length ? prices[prices.length - 1] : Math.exp(bars[bars.length - 1].p || 0);
    var pNowLog = bars[bars.length - 1].p != null ? bars[bars.length - 1].p : (priceNow > 0 ? Math.log(priceNow) : 0);
    var openPx = ctx.openPx || (prices.length ? prices[0] : priceNow);
    var rv = intradayRV(rets);
    var lam = 0.85, num = 0, den = 0, w = 1;
    for (var i = rets.length - 1; i >= 0; i--) { num += w * rets[i]; den += w; w *= lam; }
    var drift = den ? num / den : 0, mu = mean(rets);
    var sig = rets.length > 1 ? Math.sqrt(rets.reduce(function (a, r) { return a + (r - mu) * (r - mu); }, 0) / (rets.length - 1)) : Math.abs(mu) + 1e-6;
    var vp = volumePace(cumVol, elapsed, total, ctx.avgDailyVol);
    var proj = eodCloseProjection(pNowLog, drift, sig, rem, openPx);
    var totV = cumVol || 1e-9, vwap = 0;
    for (var k = 0; k < vols.length; k++) vwap += (k < prices.length ? prices[k] : priceNow) * vols[k];
    vwap /= totV;
    var avgv = ctx.avgDailyVol, hv = ctx.dailyHV;
    return {
      elapsed: elapsed, remaining: rem, priceNow: priceNow, vwap: vwap,
      pctNow: openPx ? (priceNow / openPx - 1) : null,
      cumVol: cumVol, projEodVol: vp.projEodVol, fracDone: vp.fracDone, volPace: vp.pace,
      projRVOL: (avgv && avgv > 0) ? vp.projEodVol / avgv : null,
      intradayRVann: rv.rvAnn, dailyHVann: hv, rvVsHv: (hv && hv > 0) ? rv.rvAnn / hv : null,
      volRegime: (hv && rv.rvAnn > 1.25 * hv) ? 'elevated' : ((hv && rv.rvAnn < 0.8 * hv) ? 'compressed' : 'normal'),
      projClose: proj.close, projLo: proj.lo, projHi: proj.hi,
      projPct: proj.pctClose, projPctLo: proj.pctLo, projPctHi: proj.pctHi,
      driftPerBucket: drift, sigmaPerBucket: sig
    };
  }
  var API = { intradayRV: intradayRV, todVolumeProfile: todVolumeProfile, volumePace: volumePace,
    eodCloseProjection: eodCloseProjection, eodOutlook: eodOutlook, BUCKETS_PER_DAY: BPD };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktIntradayEOD = API;
})(typeof window !== 'undefined' ? window : this);
