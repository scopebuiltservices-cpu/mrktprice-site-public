// Node cross-check of lineage.js against the Python-verified decimals.
import L from "../lineage.js";
let pass = 0, fail = 0;
function ok(name, cond) { if (cond) { pass++; } else { fail++; console.log("FAIL", name); } }
function approx(a, b, t = 1e-9) { return Math.abs(a - b) <= t; }

// viterbi recovers planted path
const li = [Math.log(.5), Math.log(.5)];
const lt = [[.9,.1],[.1,.9]].map(r => r.map(Math.log));
const planted = [0,0,1,1,1];
const ll = planted.map(z => { const r = [Math.log(.05), Math.log(.05)]; r[z] = Math.log(.95); return r; });
ok("viterbi", JSON.stringify(L.viterbi(li, lt, ll).path) === JSON.stringify(planted));

// branch decomposition
const d = L.branchDecomposition([.5,.5], [2,-2], [1,1]);
ok("branch within", approx(d.within, 1));
ok("branch between", approx(d.between, 4));
ok("branch shares", approx(d.diffusive_share, .2) && approx(d.branching_share, .8));

// bridge touch
ok("bridge breached", L.bridgeTouchUpper(0, .1, .05, .04) === 1);
ok("bridge mono", L.bridgeTouchUpper(0,0,.05,.04) > L.bridgeTouchUpper(0,0,.30,.04));
ok("bridge symmetry", approx(L.bridgeTouchUpper(0,0,.06,.04), L.bridgeTouchLower(0,0,-.06,.04)));

// sigma-volume
const m = L.sigmaVolumeMatrix(
  [{horizon:"1d",retZ:.5,cumVol:100},{horizon:"1d",retZ:1.5,cumVol:300},{horizon:"1d",retZ:1.7,cumVol:500}],
  ["1d"], [0,1,2]);
ok("sigvol bin", m["1d"]["1..2"].n === 2 && approx(m["1d"]["1..2"].meanCumVol, 400));

// conformal coverage
function randn(){let u=0,v=0;while(!u)u=Math.random();while(!v)v=Math.random();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}
const cal = Array.from({length:2000}, randn);
const pad = L.conformalPad(cal.map(y => Math.max(-1-y, y-1, 0)), .10);
const test = Array.from({length:20000}, randn);
const cov = test.filter(y => -1-pad <= y && y <= 1+pad).length / test.length;
ok("conformal coverage>=.88", cov >= .88);

// straddle ratio
const s = L.straddleLabels(100, .20, .25);
ok("straddle ratio", approx(s.sigmaEquivMove, s.impliedAbsMove*Math.sqrt(Math.PI/2)) && approx(s.sigmaEquivMove, s.sigma1Move));

// event var + house blend
ok("event var", approx(L.eventVariance(.0040,.0015,.01,.10), .0040-.0015-.001));
ok("house blend", approx(L.houseBlend(.04,.02,.001,.5), .5*.04+.5*.02+.001));
ok("house bad-liq", approx(L.houseBlend(.04,.02,0,0), .02));

// hawkes
const hb = L.hawkesExpectedCount(100, [], 2, 1, .5, 10);
const he = L.hawkesExpectedCount(100, [99,99.5], 2, 1, .5, 10);
ok("hawkes base", approx(hb.expectedCount, 20));
ok("hawkes excited", he.expectedCount > hb.expectedCount);

// driver discipline
const drv = L.driverContributions([.7,.3], [2,-1,.5], [1,2,.1], ["10Y","WTI","VIX"], ["associated","event-linked","bogus"]);
ok("driver sum", approx(drv.reduce((a,b)=>a+b.contrib,0), 1));
ok("driver coerce", drv.find(x=>x.name==="VIX").label === "associated");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
