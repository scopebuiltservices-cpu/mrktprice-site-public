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

// ---- Phase 3 calibration ----
// CRPS of N(0,1) at 0 ~ 0.233931 (erf approx -> loose tol)
ok("crps N(0,1)@0", approx(L.crpsGaussian(0,0,1), 2*(1/Math.sqrt(2*Math.PI))-1/Math.sqrt(Math.PI), 1e-4));
ok("crps grows sigma", L.crpsGaussian(0,0,2) > L.crpsGaussian(0,0,1));
ok("crps grows |y-mu|", L.crpsGaussian(5,0,1) > L.crpsGaussian(0,0,1));
// Wilson
let [wl,wh] = L.wilsonInterval(50,100);
ok("wilson centered .5", wl < .5 && .5 < wh && approx((wl+wh)/2,.5,.01));
ok("wilson k=n<=1", L.wilsonInterval(100,100)[1] <= 1);
// interval score
ok("iscore inside", approx(L.intervalScore(0,-1,1,.10), 2));
ok("iscore below", approx(L.intervalScore(-2,-1,1,.10), 2 + 20*1));
// PIT uniform vs skewed
const uni = Array.from({length:2000}, () => Math.random());
const sk = Array.from({length:2000}, () => Math.pow(Math.random(),2));
ok("pit uniform not rejected", L.pitKs(uni).p > 0.05);
ok("pit skewed rejected", L.pitKs(sk).p < 0.05);
// DKW
ok("dkw shrinks", L.dkwBand(100) > L.dkwBand(10000));
// calibrate: correct model -> coverage within Wilson CI of 0.90
const rr = Array.from({length:700}, () => 0.0005 + 0.02*randn());
const cal3 = L.calibrateHorizon(rr, 1, null, 40, 0.10);
ok("calibrate target .9", cal3.target === 0.9);
ok("calibrate coverage in CI", cal3.wilsonLo <= 0.90 && 0.90 <= cal3.wilsonHi);
ok("calibrate crps>0", cal3.crps > 0 && cal3.intervalScore > 0);

// ---- Phase 4 volume & impact ----
ok("fp reflection", approx(L.firstPassageUp(0.05,0,0.05), 2*L.normCdf(-1), 1e-9));
ok("fp monotone", L.firstPassageUp(0.02,0,0.05) > L.firstPassageUp(0.10,0,0.05));
ok("fp through", L.firstPassageUp(0,0,0.05) === 1);
ok("fp down mirror", approx(L.firstPassageDown(-0.05,0,0.05), L.firstPassageUp(0.05,0,0.05)));
ok("fp drift", L.firstPassageUp(0.05,0.02,0.05) > L.firstPassageUp(0.05,-0.02,0.05));
// volume-ahead conditioning
let px=100, rows4=[];
for (let d=0; d<400; d++){ let r=0.02*randn(); px*=Math.exp(r); let vol=Math.round(1e6*(1+6*Math.abs(r)/0.02)); rows4.push(["2020-01-01", Math.round(px*1e4)/1e4, vol]); }
const va = L.volumeAhead(rows4);
ok("volAhead outer>center", va.sigvol["1d"]["2..3"].meanCumVol > va.sigvol["1d"]["0..1"].meanCumVol);
ok("volAhead base", va.base.avgVol20>0 && va.base.dailySigma>0 && va.base.volAcf1!=null);
// touch odds
let px2=100, rows5=[];
for (let d=0; d<120; d++){ px2*=Math.exp(0.015*randn()); rows5.push(["2020-01-01", Math.round(px2*1e4)/1e4, 1000]); }
const to = L.touchOdds(rows5);
ok("touch has 20d", "20d" in to && to["20d"].pUp>=0 && to["20d"].pUp<=1);
ok("touch horizon mono", to["20d"].pUp >= to["1d"].pUp - 1e-9);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
