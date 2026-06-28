/* Exact Py<->JS parity for the corrected HARQ engine: harq_engine.js vs tools/harq_golden.json
   (from tools/market_map/harq_regime.py). volDaily, every beta (incl the HARQ interaction b1Q), r2, oosR2,
   confQ must agree to 1e-9. Run: node tools/test_harq_parity.mjs */
import { createRequire } from 'module';
import fs from 'node:fs'; import path from 'node:path'; import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const H = require('../harq_engine.js');
const fp = path.join(here, 'harq_golden.json');
if (!fs.existsSync(fp)) { console.log('SKIP: tools/harq_golden.json absent'); process.exit(0); }
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
const close = (a, b) => (a == null && b == null) || Math.abs(a - b) <= 1e-9 * (1 + Math.abs(b));
const g = JSON.parse(fs.readFileSync(fp, 'utf8'));
const j = H.forecast(g.closes), e = g.expected;
ok('harq_engine exposes forecast', typeof H.forecast === 'function');
ok('volDaily', close(j.volDaily, e.volDaily), [j.volDaily, e.volDaily]);
ok('volForecastAnn', close(j.volForecastAnn, e.volForecastAnn));
ok('r2 (in-sample)', close(j.r2, e.r2), [j.r2, e.r2]);
ok('oosR2 (walk-forward)', close(j.oosR2, e.oosR2), [j.oosR2, e.oosR2]);
ok('confQ (HARQ-residual conformal)', close(j.confQ, e.confQ), [j.confQ, e.confQ]);
ok('b1Q (HARQ interaction)', close(j.b1Q, e.b1Q), [j.b1Q, e.b1Q]);
e.beta.forEach((bv, i) => ok('beta[' + i + ']', close(j.beta[i], bv), [j.beta[i], bv]));
ok('phvNow', close(j.phvNow, e.phvNow));
console.log('\n' + (fails ? fails + ' FAILED' : 'ALL HARQ PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
