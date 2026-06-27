/* Pooled cross-sectional research estimators (browser + Node parity with pooled_research.py).
   Attaches globalThis.PooledResearch. Mirrors the Python reference 1:1 (same algorithms). */
(function(g){
'use strict';
function mean(x){return x.length?x.reduce((a,b)=>a+b,0)/x.length:0;}
function std(x,ddof){ddof=(ddof===undefined)?1:ddof;const n=x.length;if(n<=ddof)return 0;const m=mean(x);return Math.sqrt(x.reduce((a,b)=>a+(b-m)*(b-m),0)/(n-ddof));}
function rank(x){const n=x.length,idx=x.map((_,i)=>i).sort((a,b)=>x[a]-x[b]),r=new Array(n);let i=0;
  while(i<n){let j=i;while(j+1<n&&x[idx[j+1]]===x[idx[i]])j++;const avg=(i+j)/2+1;for(let k=i;k<=j;k++)r[idx[k]]=avg;i=j+1;}return r;}
function pearson(x,y){const n=Math.min(x.length,y.length);if(n<3)return 0;x=x.slice(0,n);y=y.slice(0,n);const mx=mean(x),my=mean(y);
  let sxy=0,sxx=0,syy=0;for(let i=0;i<n;i++){sxy+=(x[i]-mx)*(y[i]-my);sxx+=(x[i]-mx)*(x[i]-mx);syy+=(y[i]-my)*(y[i]-my);}return(sxx>0&&syy>0)?sxy/Math.sqrt(sxx*syy):0;}
function spearman(x,y){const n=Math.min(x.length,y.length);if(n<3)return 0;return pearson(rank(x.slice(0,n)),rank(y.slice(0,n)));}
function ncdf(z){return 0.5*(1+erf(z/Math.SQRT2));}
function erf(x){const s=x<0?-1:1;x=Math.abs(x);const t=1/(1+0.3275911*x);const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return s*y;}
function nppf(p){if(p<=0)return -1e9;if(p>=1)return 1e9;
  const a=[-3.969683028665376e+01,2.209460984245205e+02,-2.759285104469687e+02,1.383577518672690e+02,-3.066479806614716e+01,2.506628277459239e+00];
  const b=[-5.447609879822406e+01,1.615858368580409e+02,-1.556989798598866e+02,6.680131188771972e+01,-1.328068155288572e+01];
  const c=[-7.784894002430293e-03,-3.223964580411365e-01,-2.400758277161838e+00,-2.549732539343734e+00,4.374664141464968e+00,2.938163982698783e+00];
  const d=[7.784695709041462e-03,3.224671290700398e-01,2.445134137142996e+00,3.754408661907416e+00];const pl=0.02425;
  if(p<pl){const q=Math.sqrt(-2*Math.log(p));return(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);}
  if(p<=1-pl){const q=p-0.5,r=q*q;return(((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1);}
  const q=Math.sqrt(-2*Math.log(1-p));return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);}

// GAP 1
function standardize(x,method){const n=x.length;if(n<2)return x.map(()=>0);
  if(method==='rank'){const r=rank(x);return r.map(ri=>2*(ri-1)/(n-1)-1);}const m=mean(x),s=std(x);return s>0?x.map(v=>(v-m)/s):x.map(()=>0);}
function poolStandardized(groups,method){const ps=[],pr=[];groups.forEach(([sig,ret])=>{const n=Math.min(sig.length,ret.length);if(n<3)return;
  ps.push.apply(ps,standardize(sig.slice(0,n),method));pr.push.apply(pr,standardize(ret.slice(0,n),method));});return[ps,pr];}
// GAP 2
function neweyWestLrv(u,maxlags){const n=u.length,m=mean(u),e=u.map(v=>v-m);let s=e.reduce((a,b)=>a+b*b,0)/n;
  for(let L=1;L<=maxlags;L++){let gl=0;for(let t=L;t<n;t++)gl+=e[t]*e[t-L];s+=2*(1-L/(maxlags+1))*(gl/n);}return s;}
function nwMeanT(u,maxlags){const n=u.length;if(n<3)return{mean:mean(u),se:0,t:0,p:1,n:n};if(maxlags==null)maxlags=Math.max(1,Math.round(Math.pow(n,0.25)));
  const lrv=neweyWestLrv(u,maxlags),se=Math.sqrt(Math.max(lrv,0)/n),m=mean(u),t=se>0?m/se:0;return{mean:m,se:se,t:t,p:2*(1-ncdf(Math.abs(t))),n:n,maxlags:maxlags};}
function hacSlope(x,y,maxlags){const n=Math.min(x.length,y.length);if(n<5)return null;x=x.slice(0,n);y=y.slice(0,n);
  const mx=mean(x),my=mean(y),xc=x.map(v=>v-mx);let sxx=xc.reduce((a,b)=>a+b*b,0);if(sxx<=0)return null;
  let b=0;for(let i=0;i<n;i++)b+=xc[i]*(y[i]-my);b/=sxx;const a=my-b*mx;const resid=y.map((yi,i)=>yi-(a+b*x[i]));
  if(maxlags==null)maxlags=Math.max(1,Math.round(Math.pow(n,0.25)));const gg=resid.map((ri,i)=>xc[i]*ri);let S=gg.reduce((q,w)=>q+w*w,0);
  for(let L=1;L<=maxlags;L++){let gl=0;for(let t=L;t<n;t++)gl+=gg[t]*gg[t-L];S+=2*(1-L/(maxlags+1))*gl;}
  const varb=S/(sxx*sxx),se=Math.sqrt(Math.max(varb,0)),t=se>0?b/se:0;return{slope:b,se:se,t:t,p:2*(1-ncdf(Math.abs(t))),n:n,n_eff:n/(maxlags+1),r:pearson(x,y),maxlags:maxlags};}
// GAP 3
function backtestNet(positions,returns,costBps){costBps=(costBps===undefined)?5:costBps;const n=Math.min(positions.length,returns.length),c=costBps/1e4;
  const gross=[],net=[],dps=[];let prev=0;for(let i=0;i<n;i++){const dp=Math.abs(positions[i]-prev);dps.push(dp);prev=positions[i];const gI=positions[i]*returns[i];gross.push(gI);net.push(gI-c*dp);}
  const shp=a=>{const s=std(a,0);return s>0?mean(a)/s*Math.sqrt(252):0;};const mdp=mean(dps),be=mdp>0?mean(gross)/mdp:null;
  return{grossSharpe:shp(gross),netSharpe:shp(net),turnover:mdp,grossMean:mean(gross),netMean:mean(net),breakevenCost_bps:be!=null?be*1e4:null,n:n};}
// GAP 4
function meanCi(x,alpha){alpha=alpha||0.05;const n=x.length;if(n<2)return{mean:mean(x),se:0,lo:null,hi:null,n:n};const m=mean(x),se=std(x)/Math.sqrt(n),z=nppf(1-alpha/2);return{mean:m,se:se,lo:m-z*se,hi:m+z*se,n:n};}
function diffMeanCi(a,b,alpha){alpha=alpha||0.05;const na=a.length,nb=b.length,m=mean(a)-mean(b);const se=Math.sqrt((na>1?std(a)*std(a)/na:0)+(nb>1?std(b)*std(b)/nb:0)),z=nppf(1-alpha/2);return{diff:m,se:se,lo:m-z*se,hi:m+z*se,na:na,nb:nb};}
// CANONICAL 5
function rankIcSeries(panelSig,panelFwd,minNames){minNames=minNames||5;const ics=[],br=[];for(let t=0;t<Math.min(panelSig.length,panelFwd.length);t++){const sig=panelSig[t],fwd=panelFwd[t];
  const names=Object.keys(sig).filter(k=>k in fwd&&sig[k]===sig[k]&&fwd[k]===fwd[k]);if(names.length<minNames)continue;ics.push(spearman(names.map(k=>sig[k]),names.map(k=>fwd[k])));br.push(names.length);}return[ics,br];}
function icSummary(ics,breadth,maxlags){if(ics.length<3)return null;const nw=nwMeanT(ics,maxlags),sd=std(ics);const bavg=breadth&&breadth.length?mean(breadth):0;
  return{meanIC:nw.mean,icT:nw.t,icP:nw.p,hitRate:ics.filter(v=>v>0).length/ics.length,IR_periodic:sd>0?mean(ics)/sd:0,breadth:bavg,IR_law:bavg>0?mean(ics)*Math.sqrt(bavg):null,nDates:ics.length};}
// CANONICAL 6
function quantileLs(panelSig,panelFwd,q){q=q||5;const bucket=[];for(let i=0;i<q;i++)bucket.push([]);const ls=[];
  for(let t=0;t<Math.min(panelSig.length,panelFwd.length);t++){const sig=panelSig[t],fwd=panelFwd[t];const names=Object.keys(sig).filter(k=>k in fwd);if(names.length<q)continue;
    const order=names.slice().sort((a,b)=>sig[a]-sig[b]);const m=order.length,per=m/q,bmeans=[];
    for(let bi=0;bi<q;bi++){const lo=Math.round(bi*per),hi=(bi<q-1)?Math.round((bi+1)*per):m,grp=order.slice(lo,hi);if(!grp.length){bmeans.push(null);continue;}const r=mean(grp.map(k=>fwd[k]));bmeans.push(r);bucket[bi].push(r);}
    if(bmeans[0]!=null&&bmeans[q-1]!=null)ls.push(bmeans[q-1]-bmeans[0]);}
  const bavg=bucket.map(bk=>bk.length?mean(bk):null);const idx=[],vals=[];bavg.forEach((bk,i)=>{if(bk!=null){idx.push(i);vals.push(bk);}});
  const mono=idx.length>=3?spearman(idx.map(Number),vals):0;const nw=ls.length>=3?nwMeanT(ls):null;const sh=(ls.length&&std(ls)>0)?mean(ls)/std(ls)*Math.sqrt(252):0;
  return{bucketMeans:bavg,monotonicity:mono,lsMean:ls.length?mean(ls):0,lsT:nw?nw.t:0,lsP:nw?nw.p:1,lsSharpe:sh,nDates:ls.length,q:q};}
// CANONICAL 7
function regimeEdge(sig,fwd,regime,thr){thr=thr||0;const out={};const labs=Array.from(new Set(regime)).sort((a,b)=>a-b);
  labs.forEach(lab=>{const xs=[],ys=[];for(let i=0;i<sig.length;i++)if(regime[i]===lab){xs.push(sig[i]);ys.push(fwd[i]);}if(xs.length<5){out[lab]=null;return;}const up=[];for(let i=0;i<xs.length;i++)if(xs[i]>thr)up.push(ys[i]);out[lab]={ic:spearman(xs,ys),meanFwdLong:up.length?mean(up):null,n:xs.length};});
  const have=labs.filter(l=>out[l]);const diff=have.length>=2?out[have[0]].ic-out[have[have.length-1]].ic:null;return{byRegime:out,icSpread:diff};}
// CANONICAL 8
function sampleCorr(rets){const names=Object.keys(rets).filter(k=>rets[k].length>=5);if(names.length<2)return[names,[]];const n=Math.min.apply(null,names.map(k=>rets[k].length));
  const R={};names.forEach(k=>R[k]=rets[k].slice(-n));return[names,names.map(a=>names.map(b=>pearson(R[a],R[b])))];}
function ledoitWolfConstantCorr(rets){const[names,C]=sampleCorr(rets);const p=names.length;if(p<2)return[names,C,0];
  const off=[];for(let i=0;i<p;i++)for(let j=0;j<p;j++)if(i!==j)off.push(C[i][j]);const rbar=mean(off);const n=Math.min.apply(null,names.map(k=>rets[k].length));
  const pi=mean(off.map(c=>(c-rbar)*(c-rbar)));const rho_=mean(off.map(c=>((1-c*c)*(1-c*c))/n));let delta=(pi+rho_)>0?rho_/(pi+rho_):1;delta=Math.max(0,Math.min(1,delta));
  const S=[];for(let i=0;i<p;i++){S.push([]);for(let j=0;j<p;j++)S[i].push(i===j?1:(1-delta)*C[i][j]+delta*rbar);}return[names,S,delta];}
function ewmaCorr(rets,lam){lam=lam||0.94;const names=Object.keys(rets).filter(k=>rets[k].length>=5);if(names.length<2)return[names,[]];const n=Math.min.apply(null,names.map(k=>rets[k].length));
  const R={};names.forEach(k=>R[k]=rets[k].slice(-n));let w=[];for(let t=0;t<n;t++)w.push((1-lam)*Math.pow(lam,n-1-t));const sw=w.reduce((a,b)=>a+b,0);w=w.map(x=>x/sw);
  const mu={};names.forEach(k=>{let s=0;for(let t=0;t<n;t++)s+=w[t]*R[k][t];mu[k]=s;});const cov=(a,b)=>{let s=0;for(let t=0;t<n;t++)s+=w[t]*(R[a][t]-mu[a])*(R[b][t]-mu[b]);return s;};
  const v={};names.forEach(k=>v[k]=cov(k,k));return[names,names.map(a=>names.map(b=>(v[a]>0&&v[b]>0)?cov(a,b)/Math.sqrt(v[a]*v[b]):0))];}
function corrPvalue(r,n){if(Math.abs(r)>=1)return 0;if(n<4)return 1;const t=r*Math.sqrt((n-2)/(1-r*r));return 2*(1-ncdf(Math.abs(t)));}
// CANONICAL 9
function solve(A,b){const n=A.length,M=A.map((row,i)=>row.slice().concat([b[i]]));for(let c=0;c<n;c++){let piv=c;for(let r=c+1;r<n;r++)if(Math.abs(M[r][c])>Math.abs(M[piv][c]))piv=r;if(Math.abs(M[piv][c])<1e-12)return null;[M[c],M[piv]]=[M[piv],M[c]];
  for(let r=0;r<n;r++)if(r!==c){const f=M[r][c]/M[c][c];for(let k=c;k<=n;k++)M[r][k]-=f*M[c][k];}}return M.map((row,i)=>row[n]/row[i]);}
function ols(rows,y){const n=rows.length,k=rows[0].length,X=rows.map(r=>[1].concat(r)),p=k+1;
  const XtX=[];for(let i=0;i<p;i++){XtX.push([]);for(let j=0;j<p;j++){let s=0;for(let t=0;t<n;t++)s+=X[t][i]*X[t][j];XtX[i].push(s);}}
  const Xty=[];for(let i=0;i<p;i++){let s=0;for(let t=0;t<n;t++)s+=X[t][i]*y[t];Xty.push(s);}return solve(XtX,Xty);}
function famaMacbeth(panelX,panelY,maxlags){const slopes=[];for(let t=0;t<Math.min(panelX.length,panelY.length);t++){const X=panelX[t],Y=panelY[t];const names=Object.keys(X).filter(k=>k in Y);if(names.length<3)continue;
  const b=ols(names.map(k=>X[k]),names.map(k=>Y[k]));if(b)slopes.push(b);}if(slopes.length<3)return null;const kf=slopes[0].length,out=[];
  for(let j=0;j<kf;j++){const nw=nwMeanT(slopes.map(s=>s[j]),maxlags);out.push({coef:nw.mean,t:nw.t,p:nw.p});}return{intercept:out[0],lambdas:out.slice(1),nDates:slopes.length};}

g.PooledResearch={mean,std,rank,pearson,spearman,ncdf,nppf,standardize,poolStandardized,neweyWestLrv,nwMeanT,hacSlope,
  backtestNet,meanCi,diffMeanCi,rankIcSeries,icSummary,quantileLs,regimeEdge,sampleCorr,ledoitWolfConstantCorr,ewmaCorr,corrPvalue,famaMacbeth};
})(typeof globalThis!=='undefined'?globalThis:this);
