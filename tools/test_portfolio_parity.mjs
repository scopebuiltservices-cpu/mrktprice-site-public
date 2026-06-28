/* Exact Py<->JS parity: portfolio_engine.js vs tools/portfolio_golden.json. Run: node tools/test_portfolio_parity.mjs */
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const P = require('../portfolio_engine.js');
let fails = 0;
const ok = (n, c) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n); if (!c) fails++; };
const close = (a, b) => Math.abs(a - b) <= 1e-9 * (1 + Math.abs(b));
const vclose = (A, B) => A.length === B.length && A.every((x, i) => close(x, B[i]));

const g = JSON.parse(fs.readFileSync(path.join(here, 'portfolio_golden.json'), 'utf8'));
ok('portfolio_engine.js API', ['factorCov', 'mvWeightsFactor', 'projectLongOnly', 'turnoverBlend'].every(k => typeof P[k] === 'function'));
const w = P.mvWeightsFactor(g.mu, g.beta, g.sigma_m, g.sigma_idio, g.lam);
ok('w', vclose(w, g.w));
ok('proj', vclose(P.projectLongOnly(w, 0.35, 1.0), g.proj));
ok('blend', vclose(P.turnoverBlend(g.proj, [0.2, 0.2, 0.2, 0.2, 0.2], 0.5), g.blend));
const cov = P.factorCov(g.beta, g.sigma_m, g.sigma_idio);
ok('covDiag', vclose(g.beta.map((_, i) => cov[i][i]), g.covDiag));
console.log('\n' + (fails ? fails + ' FAILED' : 'ALL PORTFOLIO PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
