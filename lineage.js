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
  function quantile(xs, q){
    var s=xs.slice().sort(function(a,b){return a-b;}), n=s.length;
    if(!n) return 0; if(n===1) return s[0];
    var pos=q*(n-1), lo=Math.floor(pos), hi=Math.ceil(pos);
    if(lo===hi) return s[lo];
    return s[lo]+(s[hi]-s[lo])*(pos-lo);
  }
  // Studentized ASYMMETRIC split-conformal calibration with an H-EMBARGO between calibration and
  // test folds. 1:1 mirror of tools/market_map/lineage.py calibrate_horizon (acceptance criteria #1-#10).
  function calibrateHorizon(returns, nSteps, regimes, window, alpha){
    window = window||26; alpha = (alpha==null)?0.10:alpha;
    var r = returns.filter(function(v){return v===v;}), T=r.length, n=Math.max(1, nSteps|0);
    var z=1.6448536269514722;
    if (T < window+3*n+20) return null;
    var r3=function(x){return Math.round(x*1000)/1000;}, r4=function(x){return Math.round(x*1e4)/1e4;}, r6=function(x){return Math.round(x*1e6)/1e6;};
    var samples=[];
    for (var i=window;i<=T-n;i++){
      var win=r.slice(i-window,i), mu=_mean(win), v=_var(win);
      var muN=n*mu, sigN=Math.sqrt(Math.max(n*v,1e-12)), y=0;
      for (var t2=i;t2<i+n;t2++) y+=r[t2];
      var rg=(regimes && i<regimes.length)?regimes[i]:null;
      samples.push([i,muN,sigN,y,rg]);
    }
    var M=samples.length; if(M<30) return null;
    var cut=Math.floor(M*0.6);
    var cal=samples.slice(0,Math.max(1,cut-n)), test=samples.slice(cut+n);
    if(cal.length<15 || test.length<15) return null;
    var embargoGap=test[0][0]-cal[cal.length-1][0];
    // finite-sample split-conformal quantiles (rank-adjusted) -> marginal coverage >= 1-alpha
    var eSorted=cal.map(function(s){return (s[3]-s[1])/s[2];}).sort(function(a,b){return a-b;});
    var ne=eSorted.length;
    var qHi=eSorted[Math.min(ne,Math.max(1,Math.ceil((1-alpha/2)*(ne+1))))-1];
    var qLo=eSorted[Math.min(ne,Math.max(1,Math.floor((alpha/2)*(ne+1))))-1];
    var eaSorted=eSorted.map(function(x){return Math.abs(x);}).sort(function(a,b){return a-b;});
    var qSym=eaSorted[Math.min(ne,Math.max(1,Math.ceil((1-alpha)*(ne+1))))-1];
    // REGIME-CONDITIONED conformal: SEPARATE lower/upper finite-sample quantiles per regime from that
    // regime's OWN calibration residuals; falls back to the pooled qLo/qHi where a regime is too thin.
    var MIN_REG_CAL=20, regE={}, regQ={};
    cal.forEach(function(s){ if(s[4]!=null){ (regE[s[4]]=regE[s[4]]||[]).push((s[3]-s[1])/s[2]); } });
    Object.keys(regE).forEach(function(rg){
      var es=regE[rg]; if(es.length>=MIN_REG_CAL){
        var es2=es.slice().sort(function(a,b){return a-b;}), m=es2.length;
        var qh=es2[Math.min(m,Math.max(1,Math.ceil((1-alpha/2)*(m+1))))-1];
        var ql=es2[Math.min(m,Math.max(1,Math.floor((alpha/2)*(m+1))))-1];
        regQ[rg]=[ql,qh];
      }
    });
    var covA=0,covS=0,covG=0,covRC=0,widths=[],crps=[],isc=[],pits=[],regCov={},regRc={};
    test.forEach(function(s){
      var muN=s[1],sigN=s[2],y=s[3],rg=s[4];
      var loA=muN+qLo*sigN, hiA=muN+qHi*sigN, cA=(loA<=y&&y<=hiA)?1:0; covA+=cA;
      // regime-conditioned padded interval: regime's own quantiles when available, else pooled
      var rq=(rg!=null && regQ[rg])?regQ[rg]:[qLo,qHi];
      var loRC=muN+rq[0]*sigN, hiRC=muN+rq[1]*sigN, cRC=(loRC<=y&&y<=hiRC)?1:0; covRC+=cRC;
      var loS=muN-qSym*sigN, hiS=muN+qSym*sigN; covS+=(loS<=y&&y<=hiS)?1:0;
      var loG=muN-z*sigN, hiG=muN+z*sigN; covG+=(loG<=y&&y<=hiG)?1:0;
      widths.push(hiA-loA); crps.push(crpsGaussian(y,muN,sigN));
      isc.push(intervalScore(y,loA,hiA,alpha)); pits.push(normCdf((y-muN)/sigN));
      if(rg!=null){ (regCov[rg]=regCov[rg]||[]).push(cA); (regRc[rg]=regRc[rg]||[]).push(cRC); }
    });
    var mt=test.length, k=covA, w=wilsonInterval(k,mt);
    var byReg={}; Object.keys(regCov).forEach(function(rg){ var cs=regCov[rg]; if(cs.length>=15) byReg[rg]={n:cs.length, coverage:r3(_mean(cs))}; });
    var byRegConf={}; Object.keys(regQ).forEach(function(rg){
      var rc=regRc[rg]||[];
      byRegConf[rg]={nCal:regE[rg].length, qLo:r4(regQ[rg][0]), qHi:r4(regQ[rg][1]),
        coverage:(rc.length?r3(_mean(rc)):null)};
    });
    var ks=pitKs(pits), dk=dkwBand(mt);
    return { n:mt, nSteps:n, nCal:cal.length, embargo:n, embargoGap:embargoGap,
      coverage:r3(k/mt), wilsonLo:r3(w[0]), wilsonHi:r3(w[1]),
      coverageGaussian:r3(covG/mt), coverageSym:r3(covS/mt),
      qLo:r4(qLo), qHi:r4(qHi), target:r3(1-alpha),
      crps:r6(_mean(crps)), intervalScore:r6(_mean(isc)), widthMean:r6(_mean(widths)),
      pitKS:ks.D!=null?r3(ks.D):null, pitUniformP:ks.p!=null?r3(ks.p):null,
      dkw:dk!=null?r4(dk):null, byRegime:byReg,
      // schema-promised fields, now genuinely emitted (1:1 with lineage.py)
      conformalPad:r4(qSym-z),
      coveragePadded:r3(covRC/mt),
      regimeConditioned:(Object.keys(regQ).length>0),
      byRegimeConformal:byRegConf,
      calibrated: (w[0]<=(1-alpha) && (1-alpha)<=w[1]) };
  }


  // ---- GARCH(1,1) variance-targeting QMLE + n-step aggregation (1:1 mirror of lineage.py) ----
  function garch11Fit(returns){
    var r=returns.filter(function(v){return v===v;}), n=r.length;
    if(n<40) return null;
    var uv=_var(r); if(uv<=0) return null;
    function nll(a,b){
      if(a<0||b<0||a+b>=0.999) return 1e18;
      var om=(1-a-b)*uv, h=uv, s=0.0;
      for(var t=1;t<n;t++){ h=om+a*r[t-1]*r[t-1]+b*h; h=Math.max(h,1e-14); s+=Math.log(h)+r[t]*r[t]/h; }
      return 0.5*s;
    }
    var best=null, A=[0.02,0.05,0.08,0.12,0.16,0.20,0.25,0.30], B=[0.50,0.60,0.70,0.78,0.85,0.90,0.94,0.97];
    for(var i=0;i<A.length;i++) for(var j=0;j<B.length;j++){ var v=nll(A[i],B[j]); if(best===null||v<best[0]) best=[v,A[i],B[j]]; }
    var a=best[1], b=best[2], step=0.04;
    for(var it=0;it<6;it++){
      var improved=false;
      var ds=[-step,0,step];
      for(var x=0;x<3;x++) for(var y=0;y<3;y++){
        var na=a+ds[x], nb=b+ds[y];
        if(na<=0||nb<=0||na+nb>=0.999) continue;
        var vv=nll(na,nb);
        if(vv<best[0]){ best=[vv,na,nb]; a=na; b=nb; improved=true; }
      }
      if(!improved) step*=0.5;
    }
    a=best[1]; b=best[2];
    return {omega:(1-a-b)*uv, alpha:a, beta:b, uncondVar:uv};
  }
  function garch11NstepVar(fit, returns, n){
    var r=returns.filter(function(v){return v===v;});
    var a=fit.alpha, b=fit.beta, om=fit.omega, uv=fit.uncondVar, h=uv;
    for(var t=1;t<r.length;t++) h=om+a*r[t-1]*r[t-1]+b*h;
    var h1=om+a*r[r.length-1]*r[r.length-1]+b*h, ph=a+b, tot=0.0;
    for(var kk=0;kk<n;kk++) tot+=uv+Math.pow(ph,kk)*(h1-uv);
    return Math.max(tot,1e-14);
  }
  // ---- Challenger scorecard: walk-forward CRPS, model vs RW / empirical-HV / EWMA / GARCH / options-Q ----
  function challengerScorecard(returns, nSteps, ivAnnual, window, alpha, stepDays){
    window=window||26; alpha=(alpha==null)?0.10:alpha; stepDays=stepDays||5.0;
    var r=returns.filter(function(v){return v===v;}), T=r.length, n=Math.max(1,nSteps|0);
    if(T<window+n+10) return null;
    var lam=0.94, ew=new Array(T).fill(null);
    if(T>window){ var v0=_var(r.slice(0,window)); for(var t=window;t<T;t++){ v0=lam*v0+(1-lam)*r[t-1]*r[t-1]; ew[t]=v0; } }
    var z=1.6448536269514722;
    var sqStep=ivAnnual?(ivAnnual*Math.sqrt(stepDays/252.0)):null;
    var g=garch11Fit(r), hpath=null, ga,gb,gom,guv;
    if(g){ ga=g.alpha; gb=g.beta; gom=g.omega; guv=g.uncondVar; hpath=new Array(T).fill(guv); var hh=guv;
      for(var tt=1;tt<T;tt++){ hh=gom+ga*r[tt-1]*r[tt-1]+gb*hh; hpath[tt]=hh; } }
    var crps={model:[],rw:[],hv:[],ewma:[]};
    if(hpath!==null) crps.garch=[];
    if(sqStep) crps.q=[];
    var covs=[];
    for(var i=window;i<=T-n;i++){
      var win=r.slice(i-window,i), mu=_mean(win), sdw=Math.sqrt(Math.max(_var(win),1e-12));
      var y=0; for(var k=i;k<i+n;k++) y+=r[k]; var rt=Math.sqrt(n);
      crps.model.push(crpsGaussian(y,n*mu,sdw*rt));
      var full=r.slice(0,i), sdf=full.length>2?Math.sqrt(Math.max(_var(full),1e-12)):sdw;
      crps.rw.push(crpsGaussian(y,0,sdf*rt));
      crps.hv.push(crpsGaussian(y,0,sdw*rt));
      var sde=Math.sqrt(Math.max(ew[i]!=null?ew[i]:_var(win),1e-12));
      crps.ewma.push(crpsGaussian(y,n*mu,sde*rt));
      if(hpath!==null){ var tot=0; for(var kk=0;kk<n;kk++) tot+=guv+Math.pow(ga+gb,kk)*(hpath[i]-guv); crps.garch.push(crpsGaussian(y,n*mu,Math.sqrt(Math.max(tot,1e-14)))); }
      if(sqStep) crps.q.push(crpsGaussian(y,n*mu,sqStep*rt));
      var lo=n*mu-z*sdw*rt, hi=n*mu+z*sdw*rt; covs.push((lo<=y&&y<=hi)?1:0);
    }
    var means={}, winner=null, wbest=Infinity;
    Object.keys(crps).forEach(function(kk){ var mv=Math.round(_mean(crps[kk])*1e6)/1e6; means[kk]=mv; if(mv<wbest){ wbest=mv; winner=kk; } });
    var m=covs.length, kc=covs.reduce(function(s,x){return s+x;},0), cov=kc/m, w=wilsonInterval(kc,m);
    var calibrated=(w[0]<=(1-alpha) && (1-alpha)<=w[1]);
    var beatsRW=means.model<=means.rw, gate, reason;
    if(beatsRW&&calibrated){ gate='deployable'; reason='beats random-walk on CRPS and calibrated'; }
    else if(beatsRW){ gate='research-only'; reason='beats random-walk but miscalibrated'; }
    else { gate='research-only'; reason='no CRPS edge over a driftless random walk'; }
    return {crps:means, winner:winner, coverage:Math.round(cov*1000)/1000, wilsonLo:Math.round(w[0]*1000)/1000,
      wilsonHi:Math.round(w[1]*1000)/1000, calibrated:calibrated, beatsRW:beatsRW, gate:gate, reason:reason, n:m};
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
    pitKs: pitKs, dkwBand: dkwBand, calibrateHorizon: calibrateHorizon, quantile: quantile,
    garch11Fit: garch11Fit, garch11NstepVar: garch11NstepVar, challengerScorecard: challengerScorecard, normCdf: normCdf,
    firstPassageUp: firstPassageUp, firstPassageDown: firstPassageDown,
    volumeAhead: volumeAhead, touchOdds: touchOdds
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  root.MrktLineage = API;
})(typeof self !== "undefined" ? self : this);
