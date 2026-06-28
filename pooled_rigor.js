/* ===== MrktPrice pooled RIGOR engine (1:1 mirror of tools/market_map/pooled_rigor.py) =====
   Selection-bias + panel-dependence hardening: PSR/MinTRL, two-way clustered SE + two-way FE, PBO (CSCV),
   White Reality Check, Hansen SPA, eigenvalue effective breadth, DerSimonian-Laird meta + I2, mover
   decomposition. Exposes window.PooledRigor. Research only. */
(function (root) {
  'use strict';
  function mean(x){return x.length?x.reduce(function(a,b){return a+b;},0)/x.length:0;}
  function ncdf(z){return 0.5*(1+erf(z/Math.SQRT2));}
  function erf(x){var s=x<0?-1:1;x=Math.abs(x);var t=1/(1+0.3275911*x);
    var y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return s*y;}
  function nppf(p){if(p<=0)return -1e9;if(p>=1)return 1e9;
    var a=[-3.969683028665376e1,2.209460984245205e2,-2.759285104469687e2,1.383577518672690e2,-3.066479806614716e1,2.506628277459239e0];
    var b=[-5.447609879822406e1,1.615858368580409e2,-1.556989798598866e2,6.680131188771972e1,-1.328068155288572e1];
    var c=[-7.784894002430293e-3,-3.223964580411365e-1,-2.400758277161838e0,-2.549732539343734e0,4.374664141464968e0,2.938163982698783e0];
    var d=[7.784695709041462e-3,3.224671290700398e-1,2.445134137142996e0,3.754408661907416e0];var pl=0.02425,q,r;
    if(p<pl){q=Math.sqrt(-2*Math.log(p));return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);}
    if(p<=1-pl){q=p-0.5;r=q*q;return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);}
    q=Math.sqrt(-2*Math.log(1-p));return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);}
  function sharpe(rets){var n=rets.length;if(n<2)return null;var m=mean(rets),v=0;for(var i=0;i<n;i++)v+=(rets[i]-m)*(rets[i]-m);v/=(n-1);return v>0?m/Math.sqrt(v):null;}

  function psr(sr,n,skew,kurt,bench){skew=skew||0;kurt=kurt==null?3:kurt;bench=bench||0;
    if(n==null||n<2)return null;var den=1-skew*sr+(kurt-1)/4*sr*sr;if(den<=0)return null;
    return ncdf((sr-bench)*Math.sqrt(n-1)/Math.sqrt(den));}
  function minTRL(sr,skew,kurt,bench,prob){skew=skew||0;kurt=kurt==null?3:kurt;bench=bench||0;prob=prob||0.95;
    if(sr<=bench)return null;var z=nppf(prob),den=1-skew*sr+(kurt-1)/4*sr*sr;if(den<=0)return null;
    return 1+den*Math.pow(z/(sr-bench),2);}

  function olsXY(x,y){var n=x.length,mx=mean(x),my=mean(y),sxx=0;for(var i=0;i<n;i++)sxx+=(x[i]-mx)*(x[i]-mx);
    if(sxx<=0)return null;var b=0;for(i=0;i<n;i++)b+=(x[i]-mx)*(y[i]-my);b/=sxx;var a=my-b*mx;
    var e=[];for(i=0;i<n;i++)e.push(y[i]-(a+b*x[i]));return {a:a,b:b,e:e,mx:mx,sxx:sxx};}
  function twoWayClusterSE(x,y,gid,did){var n=x.length;if(n<5)return null;var f=olsXY(x,y);if(!f)return null;
    var xc=x.map(function(v){return v-f.mx;}),bread=1/f.sxx;
    function meat(lab){var s={};for(var i=0;i<n;i++){var k=lab[i];s[k]=(s[k]||0)+xc[i]*f.e[i];}var t=0;for(var kk in s)t+=s[kk]*s[kk];return t;}
    var Vg=bread*meat(gid)*bread,Vd=bread*meat(did)*bread,w=0;for(var i=0;i<n;i++)w+=Math.pow(xc[i]*f.e[i],2);var Vw=bread*w*bread;
    var V=Vg+Vd-Vw;if(V<=0)V=Math.max(Vg,Vd,Vw);var se=Math.sqrt(V),t=se>0?f.b/se:0;
    return {beta:f.b,se:se,t:t,p:Math.max(0,Math.min(1,2*(1-ncdf(Math.abs(t))))),n:n};}
  function twoWayFE(x,y,gid,did){var n=x.length;if(n<5)return null;
    function demean(v){var gb={},gc={},db={},dc={},i;for(i=0;i<n;i++){gb[gid[i]]=(gb[gid[i]]||0)+v[i];gc[gid[i]]=(gc[gid[i]]||0)+1;db[did[i]]=(db[did[i]]||0)+v[i];dc[did[i]]=(dc[did[i]]||0)+1;}
      var gg=mean(v),out=[];for(i=0;i<n;i++)out.push(v[i]-gb[gid[i]]/gc[gid[i]]-db[did[i]]/dc[did[i]]+gg);return out;}
    var xt=demean(x),yt=demean(y),sxx=0,sxy=0;for(var i=0;i<n;i++){sxx+=xt[i]*xt[i];sxy+=xt[i]*yt[i];}
    if(sxx<=0)return null;return {beta:sxy/sxx,n:n};}

  function effectiveBreadth(corr){var N=corr.length;if(!N)return null;var f=0;for(var i=0;i<N;i++)for(var j=0;j<N;j++)f+=corr[i][j]*corr[i][j];return f>0?(N*N)/f:null;}

  function randomEffectsMeta(betas,ses){var b=[],w=[];for(var i=0;i<betas.length;i++){if(ses[i]&&ses[i]>0&&betas[i]!=null){b.push(betas[i]);w.push(1/(ses[i]*ses[i]));}}
    var k=b.length;if(k<2)return {beta_fe:null,beta_re:null,se_re:null,tau2:null,Q:null,I2:null,k:k};
    var sw=w.reduce(function(a,c){return a+c;},0),bfe=0;for(i=0;i<k;i++)bfe+=w[i]*b[i];bfe/=sw;
    var Q=0;for(i=0;i<k;i++)Q+=w[i]*(b[i]-bfe)*(b[i]-bfe);var df=k-1;
    var sw2=0;for(i=0;i<k;i++)sw2+=w[i]*w[i];var C=sw-sw2/sw;var tau2=C>0?Math.max(0,(Q-df)/C):0;
    var ws=w.map(function(wi){var d=1/wi+tau2;return d>0?1/d:0;}),sws=ws.reduce(function(a,c){return a+c;},0);
    var bre=sws>0?(function(){var s=0;for(var i=0;i<k;i++)s+=ws[i]*b[i];return s/sws;})():null;
    return {beta_fe:bfe,beta_re:bre,se_re:sws>0?Math.sqrt(1/sws):null,tau2:tau2,Q:Q,I2:Q>0?Math.max(0,(Q-df)/Q)*100:0,k:k};}

  function moverDecomp(now,prev,weights){weights=weights||{sMR:0.35,sMom:0.30,sSig:0.25,sVol:0.10};var contrib={},total=0;
    for(var k in weights){var d=(now[k]||0)-(prev[k]||0),c=weights[k]*d;contrib[k]=c;total+=c;}return {dnet:total,contrib:contrib};}

  function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};}
  function blockIdx(T,block,rnd){var idx=[];while(idx.length<T){var s=Math.floor(rnd()*T);for(var j=0;j<block&&idx.length<T;j++)idx.push((s+j)%T);}return idx.slice(0,T);}
  function combHalves(S){var idx=[];for(var i=0;i<S;i++)idx.push(i);var half=S>>1,out=[],seen={};
    (function go(start,cur){if(cur.length===half){var key=cur.slice().sort(function(a,b){return a-b;}).join(','),comp=idx.filter(function(v){return cur.indexOf(v)<0;}),ck=comp.join(',');
      if(!seen[key]&&!seen[ck]){seen[key]=1;out.push([cur.slice(),comp]);}return;}
      for(var i=start;i<S;i++){cur.push(idx[i]);go(i+1,cur);cur.pop();}})(0,[]);return out;}
  function pboCSCV(M,S){S=S||10;var T=M.length;if(T<S||!M[0]||M[0].length<2)return {pbo:null};var N=M[0].length,bs=Math.floor(T/S),blocks=[];
    for(var k=0;k<S;k++){var blk=[];for(var r=k*bs;r<(k+1)*bs;r++)blk.push(r);blocks.push(blk);}
    function perf(rows,c){var xs=rows.map(function(r){return M[r][c];});return sharpe(xs)||0;}
    var parts=combHalves(S),lam=[];
    for(var pi=0;pi<parts.length;pi++){var IS=[],OOS=[],a;for(a=0;a<parts[pi][0].length;a++)IS=IS.concat(blocks[parts[pi][0][a]]);for(a=0;a<parts[pi][1].length;a++)OOS=OOS.concat(blocks[parts[pi][1][a]]);
      var best=0,bv=-1e18;for(var c=0;c<N;c++){var v=perf(IS,c);if(v>bv){bv=v;best=c;}}
      var ob=perf(OOS,best),rank=1;for(c=0;c<N;c++)if(perf(OOS,c)<ob)rank++;lam.push(rank/(N+1)<=0.5?1:0);}
    return {pbo:lam.length?mean(lam):null,n_splits:lam.length,n_configs:N};}
  function realityCheck(D,B,block,seed){B=B||1000;block=block||5;var T=D.length;if(T<10||!D[0])return {p:null};var K=D[0].length,cols=[],k;
    for(k=0;k<K;k++){var col=[];for(var t=0;t<T;t++)col.push(D[t][k]);cols.push(col);}var means=cols.map(mean);
    var V=-1e18;for(k=0;k<K;k++)V=Math.max(V,Math.sqrt(T)*means[k]);var rnd=mulberry32(seed||12345),ge=0;
    for(var bI=0;bI<B;bI++){var idx=blockIdx(T,block,rnd),vb=-1e18;for(k=0;k<K;k++){var mb=mean(idx.map(function(i){return cols[k][i];}));vb=Math.max(vb,Math.sqrt(T)*(mb-means[k]));}if(vb>=V)ge++;}
    return {p:(ge+1)/(B+1),V:V,K:K};}
  function spa(D,B,block,seed){B=B||1000;block=block||5;var T=D.length;if(T<10||!D[0])return {p:null};var K=D[0].length,cols=[],k;
    for(k=0;k<K;k++){var col=[];for(var t=0;t<T;t++)col.push(D[t][k]);cols.push(col);}var means=cols.map(mean),sds=[];
    for(k=0;k<K;k++){var v=0;for(var t=0;t<T;t++)v+=(cols[k][t]-means[k])*(cols[k][t]-means[k]);v/=Math.max(T-1,1);sds.push(v>0?Math.sqrt(v/T):1e-9);}
    var Ts=-1e18;for(k=0;k<K;k++)Ts=Math.max(Ts,means[k]/sds[k]);
    var thr=[];for(k=0;k<K;k++){thr.push(means[k]>=-sds[k]*Math.sqrt(2*Math.log(Math.log(T)))?means[k]:0);}
    var rnd=mulberry32(seed||777),ge=0;
    for(var bI=0;bI<B;bI++){var idx=blockIdx(T,block,rnd),tb=-1e18;for(k=0;k<K;k++){var mb=mean(idx.map(function(i){return cols[k][i];}));tb=Math.max(tb,(mb-thr[k])/sds[k]);}if(tb>=Ts)ge++;}
    return {p:(ge+1)/(B+1),T:Ts,K:K};}

  var API={sharpe:sharpe,psr:psr,minTRL:minTRL,twoWayClusterSE:twoWayClusterSE,twoWayFE:twoWayFE,
    effectiveBreadth:effectiveBreadth,randomEffectsMeta:randomEffectsMeta,moverDecomp:moverDecomp,
    pboCSCV:pboCSCV,realityCheck:realityCheck,spa:spa};
  if(typeof module!=='undefined'&&module.exports)module.exports=API;
  root.PooledRigor=API;
})(typeof window!=='undefined'?window:this);
