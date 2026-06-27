/* GARCH seed backtest harness (code-review M-stat1, part b).
   Compares the two h0 seed conventions in engine.js garch():
     'uncond'      h0 = sample unconditional variance (historical default)
     'stationary'  h0 = w/(1-a-b)  (parameter-consistent; the review's proposed fix)
   over many simulated GARCH(1,1) paths with KNOWN parameters, scoring:
     - persistence-recovery error  |kappa_hat - kappa_true|
     - 1-step-ahead out-of-sample QLIKE  (log h + r^2/h) on a held-out continuation
   so flipping the live default is a DATA-DRIVEN decision, not a guess. Default stays 'uncond' until
   the harness shows 'stationary' is decisively better. Run: node tools/test_garch_seed_backtest.mjs */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const repo = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
new Function(fs.readFileSync(path.join(repo, 'engine.js'), 'utf8'))();
const E = globalThis.MrktEngine;

function mul32(a){return function(){a|=0;a=(a+0x6D2B79F5)|0;let t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;};}
function gauss(r){let u=0,v=0;while(u===0)u=r();while(v===0)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}
function simGarch(n,w,a,b,seed){const rr=mul32(seed);let h=w/(1-a-b),out=[];for(let i=0;i<n;i++){const rt=Math.sqrt(h)*gauss(rr);out.push(rt);h=w+a*rt*rt+b*h;}return out;}

/* held-out 1-step QLIKE: roll the fitted GARCH variance recursion forward over a continuation path */
function qlikeOOS(fit, train, future, seedKind){
  let h = (seedKind==='stationary' && (1-fit.a-fit.b)>1e-6) ? fit.w/(1-fit.a-fit.b) : (train.reduce((s,x)=>s+x*x,0)/train.length);
  for(let t=1;t<train.length;t++) h = fit.w + fit.a*train[t-1]*train[t-1] + fit.b*h;   // warm up to end of train
  let q=0, prev=train[train.length-1];
  for(let t=0;t<future.length;t++){ h = fit.w + fit.a*prev*prev + fit.b*h; q += Math.log(h) + future[t]*future[t]/h; prev=future[t]; }
  return q/future.length;
}

const NS=24, TR=500, FU=120, W=2e-6, Aa=0.08, Bb=0.90, KT=Aa+Bb;
let recU=0, recS=0, qU=0, qS=0, ok2=0;
for(let s=0;s<NS;s++){
  const full=simGarch(TR+FU, W, Aa, Bb, 100+s), train=full.slice(0,TR), future=full.slice(TR);
  const gu=E.garch(train,{seed:'uncond'}), gs=E.garch(train,{seed:'stationary'});
  if(!isFinite(gu.kappa)||!isFinite(gs.kappa))continue; ok2++;
  recU+=Math.abs(gu.kappa-KT); recS+=Math.abs(gs.kappa-KT);
  qU+=qlikeOOS(gu,train,future,'uncond'); qS+=qlikeOOS(gs,train,future,'stationary');
}
recU/=ok2; recS/=ok2; qU/=ok2; qS/=ok2;
console.log(`\n  sims=${ok2}  true kappa=${KT}`);
console.log(`  persistence-recovery MAE   uncond=${recU.toFixed(4)}  stationary=${recS.toFixed(4)}  winner=${recS<recU?'stationary':'uncond'}`);
console.log(`  out-of-sample QLIKE (lower) uncond=${qU.toFixed(5)}  stationary=${qS.toFixed(5)}  winner=${qS<qU?'stationary':'uncond'}`);
const dRec=(recU-recS)/Math.max(recU,1e-9), dQ=(qU-qS)/Math.max(Math.abs(qU),1e-9);
console.log(`  relative gain of stationary: recovery ${(100*dRec).toFixed(1)}% · QLIKE ${(100*dQ).toFixed(2)}%`);
const decisive = (recS < recU*0.9) && (qS <= qU + 1e-9);   // >10% better recovery AND no worse QLIKE
console.log(`  VERDICT: ${decisive ? 'stationary decisively better -> safe to flip the live default' : 'no decisive edge -> keep default uncond (both available)'}`);

/* the harness itself must run cleanly + both seeds must produce finite, valid fits */
ok('both seed fits ran on all sims', ok2 === NS, [ok2, NS]);
ok('both recovery MAEs finite + sane (<0.2)', recU < 0.2 && recS < 0.2, [recU, recS]);
ok('both OOS QLIKE finite', isFinite(qU) && isFinite(qS), [qU, qS]);
console.log('\n' + (fails ? (fails + ' FAILED') : 'GARCH SEED BACKTEST OK (verdict above is the flip decision)'));
process.exit(fails ? 1 : 0);
