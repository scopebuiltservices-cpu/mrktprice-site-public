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
  function _erf(x){var s=x<0?-1:1;x=Math.abs(x);var t=1/(1+0.3275911*x);
    var y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return s*y;}
  function _Phi(x){return 0.5*(1+_erf(x/Math.SQRT2));}
  function todVarianceProfile(n){n=n||BPD;var w=[];
    for(var i=0;i<n;i++){var edge=Math.exp(-i/4)+Math.exp(-(n-1-i)/4);w.push(1+2.6*edge);}
    var s=w.reduce(function(a,b){return a+b;},0);return w.map(function(x){return x/s;});}
  /* 100x projClose-vs-priceNow: shrink the noisy intraday drift toward a martingale by the fraction of the
     session elapsed (early reads get less trust), size the remaining band off the U-SHAPED time-of-day
     variance budget (the close carries more variance than midday), and turn the gap into PROBABILITIES:
     P(close>now), P(green day vs prevClose), P(close>VWAP), the expected remaining move, and how much of
     the projected day-move is already done. o = eodOutlook(...) output. No look-ahead. */
  function closeVsNow(o, prevClose, total){
    if(!o)return null; total=total||BPD;
    var elapsed=o.elapsed, rem=Math.max(0,o.remaining), now=o.priceNow, vwap=o.vwap, sig=o.sigmaPerBucket||0;
    var sessFrac=total>0?elapsed/total:0, driftShrunk=(o.driftPerBucket||0)*sessFrac;
    var vprof=todVarianceProfile(total), remVarFrac=0; for(var i=elapsed;i<total;i++)remVarFrac+=(vprof[i]||0);
    var bandSig=Math.sqrt(Math.max(sig*sig*total*Math.max(remVarFrac,0),0));
    var pNow=now>0?Math.log(now):0, pMean=pNow+driftShrunk*rem, closeMean=Math.exp(pMean), z=1.6448536;
    var pUp=bandSig>0?_Phi((pMean-pNow)/bandSig):(pMean>=pNow?1:0);
    var pGreen=(prevClose>0)?(bandSig>0?_Phi((pMean-Math.log(prevClose))/bandSig):(closeMean>=prevClose?1:0)):null;
    var pVwap=(vwap>0)?(bandSig>0?_Phi((pMean-Math.log(vwap))/bandSig):(closeMean>=vwap?1:0)):null;
    var nowMove=(prevClose>0)?now/prevClose-1:null, projMove=(prevClose>0)?closeMean/prevClose-1:null;
    return {sessFrac:sessFrac, remVarFrac:remVarFrac, driftShrunk:driftShrunk, bandSig:bandSig,
      closeMean:closeMean, lo:Math.exp(pMean-z*bandSig), hi:Math.exp(pMean+z*bandSig),
      pUp:pUp, pGreen:pGreen, pVwap:pVwap,
      expRem:closeMean-now, expRemPct:(now>0?closeMean/now-1:null),
      nowMovePct:nowMove, projMovePct:projMove,
      completion:(projMove&&projMove!==0&&nowMove!=null)?nowMove/projMove:null};
  }
  var API = { intradayRV: intradayRV, todVolumeProfile: todVolumeProfile, volumePace: volumePace, todVarianceProfile: todVarianceProfile, closeVsNow: closeVsNow,
    eodCloseProjection: eodCloseProjection, eodOutlook: eodOutlook, BUCKETS_PER_DAY: BPD };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.MrktIntradayEOD = API;
})(typeof window !== 'undefined' ? window : this);
