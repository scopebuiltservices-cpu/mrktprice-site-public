// Py<->JS parity guard for the regime-conditioned conformal fields in lineage.js
// (mirror of tools/market_map/test_lineage_conformal.py). Run: node tools/test_lineage_conformal.mjs
import L from "../lineage.js";

let pass = 0, fail = 0;
function ok(name, cond) { if (cond) { pass++; } else { fail++; console.log("FAIL", name); } }

// deterministic two-vol-regime synthetic returns (calm/stormy alternating blocks)
let _s = 5;
function rng(){ _s = (_s * 1103515245 + 12345) & 0x7fffffff; return _s / 0x7fffffff; }
function randn(){ let u=0,v=0; while(!u)u=rng(); while(!v)v=rng(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }
const N = 900, r = [], regimes = [];
for (let i = 0; i < N; i++) {
  const hi = ((i / 60) | 0) % 2 === 1;
  r.push(0.0003 + (hi ? 0.03 : 0.008) * randn());
  regimes.push(hi ? 1 : 0);
}

const c = L.calibrateHorizon(r, 5, regimes);
ok("calibration not null", c != null);
["conformalPad","coveragePadded","regimeConditioned","byRegimeConformal","qLo","qHi","coverage"].forEach(function(f){
  ok("has field " + f, c && (f in c));
});
ok("coveragePadded in [0,1]", typeof c.coveragePadded === "number" && c.coveragePadded >= 0 && c.coveragePadded <= 1);
ok("regimeConditioned true", c.regimeConditioned === true);
ok("byRegimeConformal non-empty", Object.keys(c.byRegimeConformal).length >= 1);
Object.keys(c.byRegimeConformal).forEach(function(rg){
  const d = c.byRegimeConformal[rg];
  ok("regime " + rg + " has qLo/qHi", "qLo" in d && "qHi" in d && d.qHi >= d.qLo);
  ok("regime " + rg + " has nCal", typeof d.nCal === "number" && d.nCal >= 20);
});
ok("conformalPad is number", typeof c.conformalPad === "number");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
