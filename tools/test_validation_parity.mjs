/* Exact Py<->JS parity: validation_engine.js vs tools/validation_golden.json. Run: node tools/test_validation_parity.mjs */
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const V = require('../validation_engine.js');
let fails = 0;
const ok = (n, c) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n); if (!c) fails++; };
const close = (a, b) => Math.abs(a - b) <= 1e-9 * (1 + Math.abs(b));

const g = JSON.parse(fs.readFileSync(path.join(here, 'validation_golden.json'), 'utf8'));
ok('validation_engine.js API', ['purgedKfold', 'pboCscv', 'promotionGate'].every(k => typeof V[k] === 'function'));
ok('PBO matches golden', close(V.pboCscv(g.M, g.S), g.pbo));
ok('purged splits match golden', JSON.stringify(V.purgedKfold(20, 4, 2)) === JSON.stringify(g.splits));
ok('gate ok', V.promotionGate(0.99, 0.10).deployable === g.gateOk.deployable);
ok('gate low-DSR', V.promotionGate(0.80, 0.10).deployable === g.gateDsr.deployable);
ok('gate high-PBO', V.promotionGate(0.99, 0.70).deployable === g.gatePbo.deployable);
console.log('\n' + (fails ? fails + ' FAILED' : 'ALL VALIDATION PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
