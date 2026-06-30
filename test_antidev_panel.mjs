/* test_antidev_panel.mjs — verifies the terminal-side anti-deviation cone consumer (antidev_panel.js):
   identity-preserving no-op on neutral controllers, correct shift/scale/asymmetric-skew on active ones,
   passthrough on missing controllers, and sane reasoning strings. Run: node test_antidev_panel.mjs */
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const AD = require("./antidev_panel.js");

function mkPJ() {
  const path = [], p80 = [], p95 = [];
  for (let t = 1; t <= 10; t++) {
    const p = 100; path.push({ t, price: p });
    const hw80 = 0.01 * Math.sqrt(t) * 1.2815, hw95 = 0.01 * Math.sqrt(t) * 1.96;
    p80.push({ t, low: p * Math.exp(-hw80), high: p * Math.exp(hw80) });
    p95.push({ t, low: p * Math.exp(-hw95), high: p * Math.exp(hw95) });
  }
  return { path, p80, p95 };
}
function fail(m) { console.error("FAIL:", m); process.exit(1); }

// 1) identity controller -> exact no-op
let pj = mkPJ();
let o = AD.applyCorrection(pj, { active: true, biasAdj: 0, scaleAdj: 1, qLower: -1.645, qUpper: 1.645, _H: 10 }, 10);
let maxd = 0;
for (let i = 0; i < pj.path.length; i++)
  maxd = Math.max(maxd, Math.abs(o.path[i].price - pj.path[i].price), Math.abs(o.p95[i].high - pj.p95[i].high), Math.abs(o.p95[i].low - pj.p95[i].low));
if (maxd > 1e-6) fail("identity no-op drift " + maxd);

// 2) active controller -> bias shift up + wider bands + fatter upside tail
pj = mkPJ();
const ac = { active: true, biasAdj: 0.02, scaleAdj: 1.4, qLower: -1.8, qUpper: 2.6, _H: 10 };
o = AD.applyCorrection(pj, ac, 10);
const pOld = pj.path[9].price, pNew = o.path[9].price;
if (!(pNew > pOld)) fail("bias did not shift cone up");
const upOld = Math.log(pj.p95[9].high / pOld), upNew = Math.log(o.p95[9].high / pNew);
const dnOld = Math.log(pj.p95[9].low / pOld), dnNew = Math.log(o.p95[9].low / pNew);
if (!(upNew > upOld * 1.3)) fail("upper band did not widen with scale");
if (!(Math.abs(upNew / upOld) > Math.abs(dnNew / dnOld))) fail("upside tail not fatter under skew");

// 3) missing controller -> passthrough (same ref)
if (AD.applyCorrection(pj, null, 10) !== pj) fail("null controller must passthrough");

// 4) reasoning strings
const rA = AD._reason(Object.assign({ _H: 10 }, ac, { nEff: 463, nRaw: 1200, coverageRaw: 0.74, coverageAdj: 0.91, target: 0.9 }), 10);
if (!/ACTIVE/.test(rA) || !/cone shifted up/.test(rA) || !/74%/.test(rA)) fail("active reasoning wrong: " + rA);
if (!/GATED OFF/.test(AD._reason({ _H: 10, active: false, nEff: 30 }, 10))) fail("gated reasoning wrong");

console.log("ALL test_antidev_panel PASS");
