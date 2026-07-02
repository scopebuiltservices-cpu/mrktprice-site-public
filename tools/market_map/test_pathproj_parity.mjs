// test_pathproj_parity.mjs — path_projection.js must reproduce the Python golden decimal-for-decimal
// (within a tiny tolerance for the erf approximation). Locks the live Direction-Deck tile to the
// server-published n.expA.proj. Run: node tools/market_map/test_pathproj_parity.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const __dir = dirname(fileURLToPath(import.meta.url));
const root = join(__dir, '..', '..');
const require = createRequire(import.meta.url);
const PP = require(join(root, 'path_projection.js'));
const gold = JSON.parse(readFileSync(join(root, 'pathproj_golden.json'), 'utf8'));

let fail = 0;
const ok = (name, cond, extra = '') => { console.log((cond ? '  PASS ' : '  FAIL ') + name + (cond ? '' : '  ' + extra)); if (!cond) fail = 1; };
const near = (a, b, t) => a != null && b != null && Math.abs(a - b) <= t;

for (const cse of gold.cases) {
  const g = cse.proj;
  const js = PP.project(cse.closes, cse.vols, gold.H, gold.r);
  ok(`[${cse.kind}] both produced`, (g == null) === (js == null));
  if (!g || !js) continue;
  ok(`[${cse.kind}] smart matches`, g.smart === js.smart, `${g.smart} vs ${js.smart}`);
  ok(`[${cse.kind}] dir matches`, g.dir === js.dir, `${g.dir} vs ${js.dir}`);
  ok(`[${cse.kind}] pathPct matches`, near(g.pathPct, js.pathPct, 0.15), `${g.pathPct} vs ${js.pathPct}`);
  ok(`[${cse.kind}] sigmaH matches`, near(g.sigmaH, js.sigmaH, 1e-4), `${g.sigmaH} vs ${js.sigmaH}`);
  ok(`[${cse.kind}] vr/z match`, near(g.vr, js.vr, 1e-3) && near(g.z, js.z, 0.05), `${g.vr}/${g.z} vs ${js.vr}/${js.z}`);
  ok(`[${cse.kind}] peakPrice matches`, near(g.peakPrice, js.peakPrice, Math.max(1e-3, Math.abs(g.peakPrice) * 5e-5)), `${g.peakPrice} vs ${js.peakPrice}`);
  ok(`[${cse.kind}] peakPct matches`, near(g.peakPct, js.peakPct, 0.05), `${g.peakPct} vs ${js.peakPct}`);
  ok(`[${cse.kind}] timeToPeakD matches`, near(g.timeToPeakD, js.timeToPeakD, 0.1), `${g.timeToPeakD} vs ${js.timeToPeakD}`);
  ok(`[${cse.kind}] topVolMult matches`, (g.topVolMult == null && js.topVolMult == null) || near(g.topVolMult, js.topVolMult, 0.03), `${g.topVolMult} vs ${js.topVolMult}`);
  ok(`[${cse.kind}] halfLife matches`, (g.halfLife == null && js.halfLife == null) || near(g.halfLife, js.halfLife, 0.2), `${g.halfLife} vs ${js.halfLife}`);
  // Chow-Denning multiple-VR parity
  const gm = cse.vrMulti, jm = PP.vrMulti(cse.closes);
  ok(`[${cse.kind}] vrMulti both produced`, (gm == null) === (jm == null));
  if (gm && jm) {
    ok(`[${cse.kind}] vrMulti mv matches`, near(gm.mv, jm.mv, 0.02), `${gm.mv} vs ${jm.mv}`);
    ok(`[${cse.kind}] vrMulti pJoint matches`, near(gm.pJoint, jm.pJoint, 0.01), `${gm.pJoint} vs ${jm.pJoint}`);
    ok(`[${cse.kind}] vrMulti qStar/m match`, gm.qStar === jm.qStar && gm.m === jm.m, `${gm.qStar}/${gm.m} vs ${jm.qStar}/${jm.m}`);
    ok(`[${cse.kind}] vrMulti pJoint >= pointwise (more conservative)`, jm.pJoint >= (1 - (2 * PP.ncdf(jm.mv) - 1)) - 1e-9);
  }
}

console.log(fail ? '\nSOME pathproj parity checks FAILED' : '\nALL pathproj parity checks PASS');
process.exit(fail ? 1 : 0);
