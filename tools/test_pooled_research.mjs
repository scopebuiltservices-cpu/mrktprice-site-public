/* Parity test: pooled_research.js must match the Python reference (pooled_research.py) on deterministic
   inputs, verified via pooled_research_fixtures.json. Run: node test_pooled_research.mjs */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const dir = path.dirname(url.fileURLToPath(import.meta.url));
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
new Function(fs.readFileSync(path.join(dir, '..', 'pooled_research.js'), 'utf8'))();
const P = globalThis.PooledResearch;
const FX = JSON.parse(fs.readFileSync(path.join(dir, '..', 'pooled_research_fixtures.json'), 'utf8'));
const close = (a, b, tol) => Math.abs(a - b) <= (tol || 1e-9);
const arrClose = (a, b, tol) => a.length === b.length && a.every((v, i) => close(v, b[i], tol));

ok('exposes 24 estimators', Object.keys(P).length === 24, Object.keys(P).length);
ok('standardize z parity', arrClose(P.standardize([1,2,3,4,5],'z'), FX.standardize_z));
ok('standardize rank parity', arrClose(P.standardize([10,40,20,30,50],'rank'), FX.standardize_rank));

const xx=[0.2,-0.1,0.4,0.3,-0.2,0.1,0.5,-0.3,0.25,0.05,0.15,-0.05];
const nw=P.nwMeanT(xx,2);
ok('nwMeanT t parity', close(nw.t, FX.nwMeanT.t) && close(nw.se, FX.nwMeanT.se));

const hs=P.hacSlope([1,2,3,4,5,6,7,8,9,10],[1.1,1.9,3.2,3.8,5.3,5.9,7.1,8.2,8.8,10.4],3);
ok('hacSlope parity (slope,t,n_eff)', close(hs.slope,FX.hacSlope.slope)&&close(hs.t,FX.hacSlope.t)&&close(hs.n_eff,FX.hacSlope.n_eff));

const bt=P.backtestNet([1,-1,1,-1,1,1,-1,1],[0.01,-0.02,0.015,-0.01,0.02,0.005,-0.01,0.012],5);
ok('backtestNet parity (net Sharpe, turnover, breakeven)', close(bt.netSharpe,FX.backtestNet.netSharpe)&&close(bt.turnover,FX.backtestNet.turnover)&&close(bt.breakevenCost_bps,FX.backtestNet.breakevenCost_bps,1e-6));

const mc=P.meanCi([0.3,0.5,0.2,0.6,0.4,0.55,0.35],0.05);
ok('meanCi parity', close(mc.lo,FX.meanCi.lo)&&close(mc.hi,FX.meanCi.hi));
const dc=P.diffMeanCi([1.0,1.2,0.9,1.1],[0.1,0.0,0.2,-0.1],0.05);
ok('diffMeanCi parity', close(dc.lo,FX.diffMeanCi.lo)&&close(dc.hi,FX.diffMeanCi.hi));

const ps=[{A:1,B:2,C:3,D:4,E:5},{A:5,B:4,C:3,D:2,E:1},{A:2,B:4,C:1,D:5,E:3}];
const pf=[{A:0.01,B:0.02,C:0.03,D:0.04,E:0.05},{A:0.05,B:0.04,C:0.03,D:0.02,E:0.01},{A:0.02,B:0.04,C:0.01,D:0.05,E:0.03}];
const [ics,br]=P.rankIcSeries(ps,pf); const ic=P.icSummary(ics,br);
ok('icSummary parity (meanIC, IR_law)', close(ic.meanIC,FX.icSummary.meanIC)&&close(ic.IR_law,FX.icSummary.IR_law));
const ls=P.quantileLs(ps,pf,5);
ok('quantileLs parity (lsMean, monotonicity)', close(ls.lsMean,FX.quantileLs.lsMean)&&close(ls.monotonicity,FX.quantileLs.monotonicity));

const sig=[0.5,-0.3,0.8,-0.6,0.2,0.9,-0.1,0.4,-0.7,0.6,0.3,-0.2,0.7,-0.5,0.1,0.55,-0.45,0.65,-0.15,0.35];
const fwd=[0.02,-0.01,0.03,-0.02,0.01,0.04,0.0,0.015,-0.025,0.022,0.012,-0.008,0.028,-0.018,0.005,0.021,-0.016,0.026,-0.006,0.014];
const reg=[0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1];
const re=P.regimeEdge(sig,fwd,reg);
ok('regimeEdge parity (ic by regime)', close(re.byRegime[0].ic,FX.regimeEdge.byRegime['0'].ic)&&close(re.byRegime[1].ic,FX.regimeEdge.byRegime['1'].ic));

const rets={A:[0.01,-0.02,0.03,-0.01,0.02,0.0,-0.015,0.025,0.005,-0.01],B:[0.012,-0.018,0.028,-0.012,0.022,0.002,-0.013,0.024,0.006,-0.009],C:[-0.02,0.03,-0.01,0.02,-0.03,0.01,0.0,-0.02,0.015,0.005]};
const [nm,Cm,delta]=P.ledoitWolfConstantCorr(rets);
ok('Ledoit-Wolf delta + A-B parity', close(delta,FX.lw_delta)&&close(Cm[nm.indexOf('A')][nm.indexOf('B')],FX.lw_AB));
const [n2,Em]=P.ewmaCorr(rets,0.94);
ok('EWMA corr A-B parity', close(Em[n2.indexOf('A')][n2.indexOf('B')],FX.ewma_AB));
ok('corrPvalue parity', close(P.corrPvalue(0.85,50),FX.corrPvalue));

const pX=[{A:[1,2],B:[2,1],C:[3,3],D:[0,1]},{A:[2,0],B:[1,3],C:[0,2],D:[3,1]},{A:[1,1],B:[3,2],C:[2,0],D:[0,3]},{A:[2,1],B:[0,2],C:[1,3],D:[3,0]}];
const pY=pX.map(X=>{const Y={};for(const k in X)Y[k]=0.5+1.5*X[k][0]-0.8*X[k][1];return Y;});
const fm=P.famaMacbeth(pX,pY);
ok('Fama-MacBeth lambdas parity', close(fm.lambdas[0].coef,FX.fm_l1)&&close(fm.lambdas[1].coef,FX.fm_l2)&&close(fm.intercept.coef,FX.fm_int));

console.log('\n' + (fails ? fails + ' PARITY FAILURES' : 'ALL JS<->PY PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
