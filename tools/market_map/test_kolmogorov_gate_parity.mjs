// test_kolmogorov_gate_parity.mjs — lock kolmogorov_gate.js to the Python reference on identical inputs.
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const K = require('./kolmogorov_gate.js');
const gold = JSON.parse(fs.readFileSync(path.join(__dirname, 'kolmogorov_gate_golden.json'), 'utf8'));

const TOL = 1e-6;
let fails = 0, maxDiff = 0, checks = 0;
function num(name, a, b) { checks++; const d = Math.abs(a - b); if (d > maxDiff) maxDiff = d; if (d > TOL) { console.log('  FAIL ' + name + ' py=' + b + ' js=' + a); fails++; } }
function bool(name, a, b) { checks++; if (a !== b) { console.log('  FAIL ' + name + ' py=' + b + ' js=' + a); fails++; } }

for (const [name, arr] of Object.entries(gold.series)) {
  const py = gold.gates[name];
  const js = K.dualGate(arr);
  bool(name + '.passed', js.passed, py.passed);
  bool(name + '.sufficient', js.sufficient, py.sufficient);
  bool(name + '.stationary', js.stationary, py.stationary);
  bool(name + '.status', js.status === py.status, true);
  num(name + '.ksD', js.ksD, py.ksD);
  num(name + '.ksP', js.ksP, py.ksP);
  num(name + '.grade', js.grade, py.grade);
  num(name + '.nRef', js.nRef, py.nRef);
  num(name + '.nCur', js.nCur, py.nCur);
}
for (const c of gold.ksCases) {
  const js = K.ksTwoSample(c.a, c.b);
  num('ks.D', js.D, c.D);
  num('ks.p', js.p, c.p);
}

console.log('\nchecks=' + checks + '  maxAbsDiff=' + maxDiff.toExponential(2) + '  tol=' + TOL);
console.log(fails === 0 ? 'ALL KOLMOGOROV-GATE PARITY CHECKS PASSED (Py=JS)' : (fails + ' FAILED'));
process.exit(fails === 0 ? 0 : 1);
