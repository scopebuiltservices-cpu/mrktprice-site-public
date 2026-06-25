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


  // ---- Phase 3: proper scoring + split-conformal calibration ----
  var SQRT2 = Math.sqrt(2), SQRT2PI = Math.sqrt(2*Math.PI), INV_SQRT_PI = 1/Math.sqrt(Math.PI);
  function erf(x){ // Abramowitz-Stegun 7.1.26
    var s = x<0?-1:1; x = Math.abs(x);
    var t = 1/(1+0.3275911*x);
    var y = 1 - (((((1.061405429*t - 1.453152027)*t) + 1.421413741)*t - 0.284496736)*t + 0.254829592)*t*Math.exp(-x*x);
    return s*y;
  }
  function normCdf(x){ return 0.5*(1+erf(x/SQRT2)); }
  function normPdf(x){ return Math.exp(-0.5*x*x)/SQRT2PI; }
  function crpsGaussian(y, mu, sigma){
    sigma = Math.max(sigma, 1e-12); var w = (y-mu)/sigma;
    return sigma*(w*(2*normCdf(w)-1) + 2*normPdf(w) - INV_SQRT_PI);
  }
  function intervalScore(y, lo, hi, alpha){
    var s = hi-lo;
    if (y<lo) s += (2/alpha)*(lo-y); else if (y>hi) s += (2/alpha)*(y-hi);
    return s;
  }
  function wilsonInterval(k, n, z){
    z = z||1.959964; if (n<=0) return [0,1];
    var p=k/n, d=1+z*z/n, c=(p+z*z/(2*n))/d, h=(z/d)*Math.sqrt(p*(1-p)/n + z*z/(4*n*n));
    return [Math.max(0,c-h), Math.min(1,c+h)];
  }
  function pitKs(pits){
    var n=pits.length; if(!n) return {D:null,p:null,n:0};
    var s=pits.slice().sort(function(a,b){return a-b;}), D=0;
    for(var i=0;i<n;i++){ D=Math.max(D, Math.abs((i+1)/n - s[i]), Math.abs(s[i]-i/n)); }
    var lam=(Math.sqrt(n)+0.12+0.11/Math.sqrt(n))*D, p=0;
    for(var j=1;j<50;j++) p += Math.pow(-1,j-1)*Math.exp(-2*j*j*lam*lam);
    return {D:D, p:Math.max(0,Math.min(1,2*p)), n:n};
  }
  function dkwBand(n, alpha){ alpha=alpha||0.05; return n>0 ? Math.sqrt(Math.log(2/alpha)/(2*n)) : null; }
  function _mean(a){ return a.length? a.reduce(function(s,x){return s+x;},0)/a.length : 0; }
  function _var(a){ if(a.length<2) return 0; var m=_mean(a); return a.reduce(function(s,x){return s+(x-m)*(x-m);},0)/(a.length-1); }
  function calibrateHorizon(returns, nSteps, regimes, window, alpha){
    window = window||26; alpha = (alpha==null)?0.10:alpha;
    var r = returns.filter(function(v){return v===v;}), T=r.length, n=Math.max(1, nSteps|0);
    var z=1.6448536269514722;
    if (T < window+n+5) return null;
    var covs=[],crps=[],isc=[],pits=[],nonconf=[],regCov={};
    for (var i=window;i<=T-n;i++){
      var win=r.slice(i-window,i), mu=_mean(win), v=_var(win);
      var muN=n*mu, sigN=Math.sqrt(Math.max(n*v,1e-12)), y=0;
      for (var t2=i;t2<i+n;t2++) y+=r[t2];
      var lo=muN-z*sigN, hi=muN+z*sigN, c=(lo<=y&&y<=hi)?1:0;
      covs.push(c); crps.push(crpsGaussian(y,muN,sigN)); isc.push(intervalScore(y,lo,hi,alpha));
      pits.push(normCdf((y-muN)/sigN)); nonconf.push(Math.max(lo-y,y-hi,0));
      if (regimes && i<regimes.length){ (regCov[regimes[i]]=regCov[regimes[i]]||[]).push(c); }
    }
    var m=covs.length; if(!m) return null;
    var k=covs.reduce(function(s,x){return s+x;},0), w=wilsonInterval(k,m), pad=conformalPad(nonconf,alpha), kp=0;
    for (i=window;i<=T-n;i++){
      var win2=r.slice(i-window,i), mu2=_mean(win2), v2=_var(win2);
      var muN2=n*mu2, sigN2=Math.sqrt(Math.max(n*v2,1e-12)), y2=0;
      for (t2=i;t2<i+n;t2++) y2+=r[t2];
      if (muN2-z*sigN2-pad<=y2 && y2<=muN2+z*sigN2+pad) kp++;
    }
    var byReg={}; Object.keys(regCov).forEach(function(rg){ var cs=regCov[rg]; if(cs.length>=15) byReg[rg]={n:cs.length, coverage:Math.round(_mean(cs)*1000)/1000}; });
    var ks=pitKs(pits);
    return { n:m, nSteps:n, coverage:Math.round(k/m*1000)/1000, wilsonLo:Math.round(w[0]*1000)/1000,
      wilsonHi:Math.round(w[1]*1000)/1000, target:Math.round((1-alpha)*1000)/1000,
      crps:crps.length?_mean(crps):0, intervalScore:_mean(isc),
      pitKS:ks.D!=null?Math.round(ks.D*1000)/1000:null, pitUniformP:ks.p!=null?Math.round(ks.p*1000)/1000:null,
      conformalPad:pad, coveragePadded:Math.round(kp/m*1000)/1000, dkw:dkwBand(m), byRegime:byReg,
      calibrated: Math.abs(k/m-(1-alpha))<=0.05 };
  }


  // ---- Phase 4: first-passage touch + volume-ahead (sigma-volume) ----
  function firstPassageUp(a, mu, sigma){
    if (a<=0) return 1; if (sigma<=0) return 0;
    var t1=normCdf((mu-a)/sigma);
    var t2=Math.exp(Math.min(2*mu*a/(sigma*sigma),700))*normCdf((-mu-a)/sigma);
    return Math.max(0, Math.min(1, t1+t2));
  }
  function firstPassageDown(a, mu, sigma){ if (a>=0) return 1; return firstPassageUp(-a,-mu,sigma); }
  function _logReturns(c){ var o=[]; for(var i=1;i<c.length;i++){ if(c[i-1]>0&&c[i]>0) o.push(Math.log(c[i]/c[i-1])); } return o; }
  function volumeAhead(rows, horizons, sigmaBins){
    horizons=horizons||HORIZONS; sigmaBins=sigmaBins||[-3,-2,-1,0,1,2,3];
    var closes=[], vols=[];
    rows.forEach(function(r){ if(r[1]!=null){ closes.push(+r[1]); vols.push(r.length>2&&r[2]!=null?+r[2]:0); } });
    if (closes.length<40) return {sigvol:{}, base:{}};
    var lr=_logReturns(closes), sd=lr.length>2?Math.sqrt(_var(lr)):0, paths=[], labels=[];
    horizons.forEach(function(H){ var label=H[0], h=Math.max(1,Math.round(H[1])); labels.push(label);
      var denom=(sd*Math.sqrt(h))||1e-9;
      for(var i=0;i<closes.length-h;i++){ if(closes[i]<=0||closes[i+h]<=0) continue;
        var rh=Math.log(closes[i+h]/closes[i]), cum=0; for(var j=i+1;j<=i+h;j++) cum+=vols[j];
        paths.push({horizon:label, retZ:rh/denom, cumVol:cum}); } });
    var sv=sigmaVolumeMatrix(paths, labels, sigmaBins);
    Object.keys(sv).forEach(function(h){ Object.keys(sv[h]).forEach(function(b){ var mv=sv[h][b].meanCumVol; if(mv!=null) sv[h][b].meanCumVol=Math.round(mv); }); });
    var last20=vols.slice(-20), logv=vols.filter(function(v){return v>0;}).map(Math.log), acf1=null;
    if(logv.length>5){ var m=_mean(logv), num=0, den=0; for(var k=1;k<logv.length;k++) num+=(logv[k]-m)*(logv[k-1]-m); for(var q=0;q<logv.length;q++) den+=(logv[q]-m)*(logv[q]-m); acf1=num/(den||1e-9); }
    var srt=vols.slice().sort(function(a,b){return a-b;});
    return {sigvol:sv, base:{ avgVol20:last20.length?Math.round(_mean(last20)):null, medVol:vols.length?Math.round(srt[srt.length>>1]):null,
      volOfVol:logv.length>2?Math.round(Math.sqrt(_var(logv))*1e4)/1e4:null, volAcf1:acf1!=null?Math.round(acf1*1e4)/1e4:null, dailySigma:Math.round(sd*1e6)/1e6 }};
  }
  function touchOdds(rows, horizons, lookback, muPerDay){
    horizons=horizons||HORIZONS; lookback=lookback||20; muPerDay=muPerDay||0;
    var closes=[]; rows.forEach(function(r){ if(r[1]!=null) closes.push(+r[1]); });
    if (closes.length<lookback+5) return {};
    var S=closes[closes.length-1], lr=_logReturns(closes), sd=lr.length>2?Math.sqrt(_var(lr)):0;
    var win=closes.slice(-lookback), hi=Math.max.apply(null,win), lo=Math.min.apply(null,win), out={};
    horizons.forEach(function(H){ var label=H[0], h=Math.max(1,Math.round(H[1])), muH=muPerDay*h, sigH=sd*Math.sqrt(h);
      var aUp=(hi>S&&S>0)?Math.log(hi/S):null, aDn=(lo<S&&S>0)?Math.log(lo/S):null;
      out[label]={ pUp:aUp!=null?Math.round(firstPassageUp(aUp,muH,sigH)*1e4)/1e4:1, pDn:aDn!=null?Math.round(firstPassageDown(aDn,muH,sigH)*1e4)/1e4:1,
        levelHigh:Math.round(hi*1e4)/1e4, levelLow:Math.round(lo*1e4)/1e4, S:Math.round(S*1e4)/1e4 }; });
    return out;
  }

  var API = {
    HORIZONS: HORIZONS, viterbi: viterbi, topBranches: topBranches,
    branchDecomposition: branchDecomposition, bridgeTouchUpper: bridgeTouchUpper,
    bridgeTouchLower: bridgeTouchLower, sigmaVolumeMatrix: sigmaVolumeMatrix,
    conformalPad: conformalPad, hawkesExpectedCount: hawkesExpectedCount,
    straddleLabels: straddleLabels, eventVariance: eventVariance, houseBlend: houseBlend,
    driverContributions: driverContributions, DRIVER_LABELS: DRIVER_LABELS,
    crpsGaussian: crpsGaussian, intervalScore: intervalScore, wilsonInterval: wilsonInterval,
    pitKs: pitKs, dkwBand: dkwBand, calibrateHorizon: calibrateHorizon, normCdf: normCdf,
    firstPassageUp: firstPassageUp, firstPassageDown: firstPassageDown,
    volumeAhead: volumeAhead, touchOdds: touchOdds
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  root.MrktLineage = API;
})(typeof self !== "undefined" ? self : this);
