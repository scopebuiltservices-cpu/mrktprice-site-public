/* Exact Py<->JS parity for the ranking engine: rank_engine.js vs the committed tools/rank_golden.json
   (from tools/market_map/rank_engine.py). Confidence-adjusted score must agree to 1e-9 across languages.
   Run: node tools/test_rank_parity.mjs */
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const R = require('../rank_engine.js');
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
const close = (a, b) => Math.abs(a - b) <= 1e-9 * (1 + Math.abs(b));

const g = JSON.parse(fs.readFileSync(path.join(here, 'rank_golden.json'), 'utf8'));
ok('rank_engine.js exposes API', ['alphaForecastSe', 'convictionSigma', 'lcbScore', 'compositeRankScore', 'deflatedConviction', 'steinShrink', 'grinoldKahn'].every(k => typeof R[k] === 'function'));
g.rows.forEach(function (row, i) {
  const cs = R.convictionSigma(row.base_sigma, row.z);
  ok('convSigma[' + i + ']', close(cs, row.convSigma), [cs, row.convSigma]);
  ok('lcb[' + i + ']', close(R.lcbScore(row.tot, row.se, g.k), row.lcb), [R.lcbScore(row.tot, row.se, g.k), row.lcb]);
  ok('score[' + i + ']', close(R.compositeRankScore(row.tot, row.z, row.base_sigma, g.k, g.n_tests, null, 1, row.se), row.score));
  ok('aFse[' + i + ']', close(R.alphaForecastSe(2.0, row.z, 0.0, 10.0, g.n_tests), row.aFse));
  ok('steinC[' + i + ']', close(R.steinShrink(row.tot, row.se, 3.0, 1.0), row.steinC));
  ok('zAdj[' + i + ']', close(R.deflatedConviction(row.z, 150), row.zAdj));
  ok('gk[' + i + ']', close(R.grinoldKahn(0.08, row.base_sigma, row.z), row.gk));
});
console.log('\n' + (fails ? fails + ' FAILED' : 'ALL RANK PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
