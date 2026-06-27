/* Quarterly stock-timeline metrics (browser port; parity with quarterly_timeline.py).
   Attaches globalThis.QTimeline. Mirrors the Python reference 1:1 for the panel-facing estimators. */
(function(g){
'use strict';
function mean(x){return x.length?x.reduce((a,b)=>a+b,0)/x.length:0;}
function std(x,ddof){ddof=(ddof===undefined)?1:ddof;var n=x.length;if(n<=ddof)return 0;var m=mean(x);return Math.sqrt(x.reduce((a,b)=>a+(b-m)*(b-m),0)/(n-ddof));}
function pearson(x,y){var n=Math.min(x.length,y.length);if(n<3)return 0;x=x.slice(0,n);y=y.slice(0,n);var mx=mean(x),my=mean(y),sxy=0,sxx=0,syy=0;for(var i=0;i<n;i++){sxy+=(x[i]-mx)*(y[i]-my);sxx+=(x[i]-mx)*(x[i]-mx);syy+=(y[i]-my)*(y[i]-my);}return(sxx>0&&syy>0)?sxy/Math.sqrt(sxx*syy):0;}
function ncdf(z){return 0.5*(1+erf(z/Math.SQRT2));}
function erf(x){var s=x<0?-1:1;x=Math.abs(x);var t=1/(1+0.3275911*x);var y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return s*y;}
function olsConst(X,y){var n=X.length,k=X[0].length,D=X.map(r=>[1].concat(r)),p=k+1;
  var XtX=[];for(var i=0;i<p;i++){XtX.push([]);for(var j=0;j<p;j++){var s=0;for(var t=0;t<n;t++)s+=D[t][i]*D[t][j];XtX[i].push(s);}}
  var Xty=[];for(i=0;i<p;i++){s=0;for(t=0;t<n;t++)s+=D[t][i]*y[t];Xty.push(s);}
  var b=solve(XtX,Xty);if(!b)return null;var resid=y.map((yt,tt)=>yt-D[tt].reduce((a,dv,j)=>a+b[j]*dv,0));return{coef:b,resid:resid,n:n,k:p};}
function solve(A,b){var n=A.length,M=A.map((row,i)=>row.slice().concat([b[i]]));for(var c=0;c<n;c++){var piv=c;for(var r=c+1;r<n;r++)if(Math.abs(M[r][c])>Math.abs(M[piv][c]))piv=r;if(Math.abs(M[piv][c])<1e-12)return null;var tm=M[c];M[c]=M[piv];M[piv]=tm;for(r=0;r<n;r++)if(r!==c){var f=M[r][c]/M[c][c];for(var k=c;k<=n;k++)M[r][k]-=f*M[c][k];}}return M.map((row,i)=>row[n]/row[i]);}

function normalized(s,base){base=base||100;if(!s.length||s[0]===0)return s.map(()=>base);return s.map(v=>base*v/s[0]);}
function logReturns(s){var o=[];for(var i=1;i<s.length;i++)if(s[i-1]>0&&s[i]>0)o.push(Math.log(s[i]/s[i-1]));return o;}
function relativeStrength(stock,bench,base){base=base||100;var ns=normalized(stock,base),nb=normalized(bench,base),n=Math.min(ns.length,nb.length),rsl=[];for(var i=0;i<n;i++)rsl.push(nb[i]?ns[i]/nb[i]:1);return{RSL:rsl,RS:rsl.map(v=>v-1)};}
function drawdowns(s){var peak=s.length?s[0]:0,dd=[],ep=[],cur=null;for(var t=0;t<s.length;t++){var x=s[t];if(x>peak)peak=x;var d=peak?x/peak-1:0;dd.push(d);
  if(d<0&&cur===null)cur={start:t,trough:t,troughVal:d,peak:peak};
  else if(d<0&&cur!==null){if(d<cur.troughVal){cur.trough=t;cur.troughVal=d;}}
  else if(d>=0&&cur!==null){cur.recovery=t;cur.recoveryDays=t-cur.trough;ep.push(cur);cur=null;}}
  if(cur!==null){cur.recovery=null;cur.recoveryDays=null;ep.push(cur);}
  var maxdd=dd.length?Math.min.apply(null,dd):0,avgdd=ep.length?mean(ep.map(e=>e.troughVal)):0;
  return{dd:dd,maxDD:maxdd,avgDD:avgdd,episodes:ep};}
function realizedVol(r,K){K=K||252;return r.length>1?Math.sqrt(K)*std(r):0;}
function downsideVol(r,K){K=K||252;var dn=r.filter(v=>v<0);return dn.length>1?Math.sqrt(K)*std(dn):0;}
function betaMarketModel(sr,mr,rf,hac){rf=rf||0;hac=(hac===undefined)?true:hac;var n=Math.min(sr.length,mr.length);if(n<5)return null;
  var y=[],x=[];for(var i=0;i<n;i++){y.push(sr[i]-rf);x.push(mr[i]-rf);}var fit=olsConst(x.map(xi=>[xi]),y);if(!fit)return null;
  var a=fit.coef[0],b=fit.coef[1],resid=fit.resid,mx=mean(x),sxx=0;for(i=0;i<n;i++)sxx+=(x[i]-mx)*(x[i]-mx);var se_b;
  if(hac){var maxlags=Math.max(1,Math.round(Math.pow(n,0.25))),gg=[];for(i=0;i<n;i++)gg.push((x[i]-mx)*resid[i]);var S=gg.reduce((q,w)=>q+w*w,0);
    for(var L=1;L<=maxlags;L++){var gl=0;for(var tt=L;tt<n;tt++)gl+=gg[tt]*gg[tt-L];S+=2*(1-L/(maxlags+1))*gl;}se_b=sxx>0?Math.sqrt(S/(sxx*sxx)):0;}
  else{var s2=resid.reduce((q,w)=>q+w*w,0)/(n-2);se_b=sxx>0?Math.sqrt(s2/sxx):0;}
  var t_b=se_b>0?b/se_b:0;return{alpha:a,beta:b,se_beta:se_b,t_beta:t_b,p_beta:2*(1-ncdf(Math.abs(t_b))),n:n,corr:pearson(x,y),r2:pearson(x,y)*pearson(x,y)};}
var EVENT_WINDOWS=[[-1,1],[0,1],[0,5],[-1,20]];
function mapEventSession(f){return((f||'').toUpperCase()==='AMC')?1:0;}
function eventStudy(sr,mr,ev,est,windows){est=est||[-250,-30];windows=windows||EVENT_WINDOWS;var e0=ev+est[0],e1=ev+est[1];
  if(e0<0||e1>=sr.length||e1<=e0+5)return null;var ys=sr.slice(e0,e1+1),xs=mr.slice(e0,e1+1),fit=olsConst(xs.map(xi=>[xi]),ys);if(!fit)return null;
  var a=fit.coef[0],b=fit.coef[1];function AR(t){return(t>=0&&t<sr.length)?sr[t]-(a+b*mr[t]):null;}
  var cars={};windows.forEach(function(w){var ars=[];for(var k=w[0];k<=w[1];k++)ars.push(AR(ev+k));cars[w[0]+','+w[1]]=ars.some(v=>v===null)?null:ars.reduce((p,q)=>p+q,0);});
  return{alpha:a,beta:b,AR_event:AR(ev),CAR:cars,estN:ys.length};}
function carSignificance(cars){var c=cars.filter(v=>v!=null);if(c.length<3)return null;var m=mean(c),se=std(c)/Math.sqrt(c.length),t=se>0?m/se:0;return{meanCAR:m,t:t,p:2*(1-ncdf(Math.abs(t))),n:c.length};}
function ewmaOverlay(x,span){span=span||20;if(!x.length)return[];var lam=2/(span+1),s=[x[0]];for(var t=1;t<x.length;t++)s.push(lam*x[t]+(1-lam)*s[s.length-1]);return s;}
function returnDecomposition(p0,p1,e0,e1,dps){if(!(p0&&e0&&e1&&p1))return null;var pe0=p0/e0,pe1=p1/e1;return{fundamentalGrowth:e1/e0-1,multipleChange:pe1/pe0-1,distributions:dps/p0,totalReturn:p1/p0-1+dps/p0};}

g.QTimeline={mean:mean,std:std,pearson:pearson,normalized:normalized,logReturns:logReturns,relativeStrength:relativeStrength,
  drawdowns:drawdowns,realizedVol:realizedVol,downsideVol:downsideVol,betaMarketModel:betaMarketModel,
  EVENT_WINDOWS:EVENT_WINDOWS,mapEventSession:mapEventSession,eventStudy:eventStudy,carSignificance:carSignificance,
  ewmaOverlay:ewmaOverlay,returnDecomposition:returnDecomposition};
})(typeof globalThis!=='undefined'?globalThis:this);
