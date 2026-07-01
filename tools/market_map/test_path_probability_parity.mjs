// test_path_probability_parity.mjs — lock path_probability.js to the Python reference via the golden
// fixture. Python is authoritative (path_probability_golden.json, produced by gen_path_golden.py).
// JS uses an Abramowitz-Stegun erf (~1.5e-7), so parity is asserted at 5e-6 abs — tight enough that any
// real porting error (wrong formula) fails by orders of magnitude, while tolerating the erf approximation.
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const PP = require('./path_probability.js');

const TOL = 5e-6;
const gold = JSON.parse(fs.readFileSync(path.join(__dirname, 'path_probability_golden.json'), 'utf8'));

let fails = 0, maxDiff = 0, checks = 0;
function eq(name, a, b) {
  checks++;
  if (a == null || b == null) { console.log('  FAIL  ' + name + ' (null)'); fails++; return; }
  const d = Math.abs(a - b); if (d > maxDiff) maxDiff = d;
  if (d > TOL) { console.log('  FAIL  ' + name + '  py=' + b + ' js=' + a + ' d=' + d); fails++; }
}

for (const c of gold.cases) {
  const { s, m, b, k } = c.in;
  eq('touchUp', PP.touchUp(b, s, m), c.touchUp);
  eq('touchDown', PP.touchDown(-Math.abs(b), s, m), c.touchDown);
  eq('eMFE', PP.expectedMaxFavorable(s, m), c.eMFE);
  eq('eMAE', PP.expectedMaxAdverse(s, m), c.eMAE);
  eq('q90', PP.runningMaxQuantile(0.90, s, m), c.q90);
  eq('q50', PP.runningMaxQuantile(0.50, s, m), c.q50);
  eq('pCond', PP.probEndAboveGivenTouchUp(Math.abs(b), k, s, Math.abs(m) < 1e-15 ? m : 0.0), c.pCond);
}
for (const r of gold.reports) {
  const { s0, sig, T, bu, bd, lv } = r.in;
  const js = PP.pathReport(s0, sig, T, bu, bd, lv, 0.0);
  for (const key of ['mfePrice', 'maePrice', 'touchUp', 'touchDn', 'pEndAboveGivenTouchUp']) {
    if (r.out[key] != null) eq('report.' + key, js[key], r.out[key]);
  }
}

console.log('\nchecks=' + checks + '  maxAbsDiff=' + maxDiff.toExponential(2) + '  tol=' + TOL);
console.log(fails === 0 ? 'ALL PATH-PROBABILITY PARITY CHECKS PASSED (Py=JS)' : (fails + ' FAILED'));
process.exit(fails === 0 ? 0 : 1);
