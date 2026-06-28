/* Exact Py<->JS parity for the full-complex macro engine: macro_tilt.js vs tools/macro_golden.json
   (from tools/market_map/macro_tilt.py). Every commodity beta, the DXY/VIX betas, and the real-rate
   curve contribution must agree to 1e-9. Run: node tools/test_macro_parity.mjs */
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const M = require('../macro_tilt.js');
const fp = path.join(here, 'macro_golden.json');
if (!fs.existsSync(fp)) { console.log('SKIP: tools/macro_golden.json absent (seed via `python3 tools/market_map/macro_tilt.py`)'); process.exit(0); }
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
const close = (a, b) => Math.abs(a - b) <= 1e-9 * (1 + Math.abs(b));

const g = JSON.parse(fs.readFileSync(fp, 'utf8'));
ok('macro_tilt.js exposes API', ['macroTilt', 'rateRealTilt', 'combinedTilt'].every(k => typeof M[k] === 'function'));
g.rows.forEach(function (r, i) {
  ok('macroTilt[' + i + ']', close(M.macroTilt(r.betas, r.moves), r.macroTilt), [M.macroTilt(r.betas, r.moves), r.macroTilt]);
  ok('macroTiltExRate[' + i + ']', close(M.macroTilt(r.betas, r.moves, ['MKT', 'RATE']), r.macroTiltExRate));
  ok('rateRealTilt[' + i + ']', close(M.rateRealTilt(r.rate, r.ratemove), r.rateRealTilt));
  ok('combined[' + i + ']', close(M.combinedTilt(r.betas, r.moves, r.rate, r.ratemove, g.w_real), r.combined), [M.combinedTilt(r.betas, r.moves, r.rate, r.ratemove, g.w_real), r.combined]);
});
console.log('\n' + (fails ? fails + ' FAILED' : 'ALL MACRO PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
