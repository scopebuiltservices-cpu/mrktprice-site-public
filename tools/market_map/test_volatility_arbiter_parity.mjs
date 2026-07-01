// test_volatility_arbiter_parity.mjs — lock volatility_arbiter.js to the Python reference.
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const VA = require('./volatility_arbiter.js');
const g = JSON.parse(fs.readFileSync(path.join(__dirname, 'va_golden.json'), 'utf8'));

const TOL = 1e-9;
let fails = 0, checks = 0, maxDiff = 0;
function num(name, a, b) {
  checks++; const d = Math.abs(a - b); if (d > maxDiff) maxDiff = d;
  if (d > TOL) { console.log('  FAIL ' + name + ' py=' + b + ' js=' + a); fails++; }
}

for (const c of g.cases) {
  const comps = c.physical.map(p => VA.component(p[0], p[1], p[2], p[3], p[4]));
  const opt = {}; for (const k in c.kw) opt[k] = c.kw[k];
  const r = VA.blend(comps, opt);
  num(c.name + '.sigma', r.sigma, c.sigma);
  num(c.name + '.sigma2', r.sigma2, c.sigma2);
  num(c.name + '.reliability', r.reliability, c.reliability);
  for (const w in c.weights) num(c.name + '.w.' + w, r.weights[w], c.weights[w]);
}
for (const v of g.vrLambda) num('vrLambda(' + v.args.join(',') + ')', VA.vrLambda(v.args[0], v.args[1], v.args[2], v.args[3]), v.val);

console.log('\nchecks=' + checks + '  maxAbsDiff=' + maxDiff.toExponential(2) + '  tol=' + TOL);
console.log(fails === 0 ? 'ALL VOL-ARBITER PARITY CHECKS PASSED (Py=JS)' : (fails + ' FAILED'));
process.exit(fails === 0 ? 0 : 1);
