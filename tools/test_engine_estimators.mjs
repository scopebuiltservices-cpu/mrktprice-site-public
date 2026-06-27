/* Planted-structure parity tests for the estimators now living in engine.js (GARCH, OU, EMA, realized
   vol). Loads the REAL engine.js (globalThis.MrktEngine) so this is authoritative. Run: node tools/test_engine_estimators.mjs */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const repo = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
new Function(fs.readFileSync(path.join(repo, 'engine.js'), 'utf8'))();
const E = globalThis.MrktEngine;

/* deterministic gaussian (Box-Muller on mulberry32) */
function mul32(a){return function(){a|=0;a=(a+0x6D2B79F5)|0;let t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;};}
function gauss(r){let u=0,v=0;while(u===0)u=r();while(v===0)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}

ok('engine exposes garch/ouFit/ema/hvRollSeries', ['garch','ouFit','ema','emaProjPath','hvRollSeries'].every(k=>typeof E[k]==='function'));

/* 1) EMA matches a manual exponential moving average exactly */
const c=[10,11,12,11,13,14,13,15]; const e=E.ema(c,4); const A=2/5; let man=c[0],okE=Math.abs(e[0]-man)<1e-12;
for(let i=1;i<c.length;i++){man=A*c[i]+(1-A)*man;if(Math.abs(e[i]-man)>1e-12)okE=false;}
ok('ema == manual EMA recursion', okE, [e[e.length-1], man]);
ok('emaProjPath length + damped sum', (()=>{const p=E.emaProjPath(0.5,100,5,0.9);return p.length===5 && Math.abs(p[0].price-100.5)<1e-9 && p[4].price>p[0].price;})());

/* 2) realized vol: hvRollSeries == manual sd*sqrt(252) over the window */
const r=[0.01,-0.008,0.012,-0.005,0.006,-0.011,0.009,0.003];
const hv=E.hvRollSeries(r,4);
function manSd(a){const m=a.reduce((x,y)=>x+y,0)/a.length;return Math.sqrt(a.reduce((s,y)=>s+(y-m)*(y-m),0)/(a.length-1));}
ok('hvRollSeries == manual sd*sqrt(252)', Math.abs(hv[0]-manSd(r.slice(0,4))*Math.sqrt(252))<1e-9, [hv[0]]);

/* 3) OU: recover a planted AR(1) phi=0.7 (stationary, mean-reverting) */
const rng=mul32(7); const phiTrue=0.7; let x=0; const xs=[];
for(let i=0;i<600;i++){x=phiTrue*x+gauss(rng); xs.push(x);}
const ou=E.ouFit(xs);
ok('OU recovers phi ~0.7', Math.abs(ou.phi-phiTrue)<0.12, ou.phi);
ok('OU flags mean-reversion', ou.meanRev===true, ou);
ok('OU half-life positive + finite', ou.halfLife>0 && isFinite(ou.halfLife), ou.halfLife);

/* 4) GARCH: recover persistence on a planted GARCH(1,1) (omega,alpha,beta)=(2e-6,0.08,0.90), kappa=0.98 */
function simGarch(n,w,a,b,seed){const rr=mul32(seed);let h=w/(1-a-b),out=[];for(let i=0;i<n;i++){const rt=Math.sqrt(h)*gauss(rr);out.push(rt);h=w+a*rt*rt+b*h;}return out;}
const g=E.garch(simGarch(1500,2e-6,0.08,0.90,11));
ok('GARCH default seed is uncond (unchanged behavior)', g.seedKind==='uncond', g.seedKind);
ok('GARCH recovers high persistence (kappa>0.85)', g.kappa>0.85 && g.kappa<1.0, g.kappa);
ok('GARCH a,b in valid range', g.a>=0 && g.b>0 && (g.a+g.b)<1, [g.a,g.b]);
ok('GARCH annVol positive + finite', g.annVol>0 && isFinite(g.annVol), g.annVol);
/* stationary-seed option runs and stays in range (evaluated by the backtest harness) */
const gS=E.garch(simGarch(1500,2e-6,0.08,0.90,11),{seed:'stationary'});
ok('GARCH stationary-seed option runs', gS.seedKind==='stationary' && gS.kappa>0.85 && gS.kappa<1.0, gS.kappa);

console.log('\n' + (fails ? (fails + ' FAILED') : 'ALL ENGINE-ESTIMATOR TESTS PASSED'));
process.exit(fails ? 1 : 0);
