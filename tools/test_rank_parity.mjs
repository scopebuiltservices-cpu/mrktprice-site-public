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
ok('rank_engine.js exposes API', ['alphaForecastSe', 'convictionSigma', 'lcbScore', 'compositeRankScore', 'deflatedConviction', 'steinShrink', 'ebTau2', 'ebPosterior', 'grinoldKahn', 'effectiveBreadth', 'enbEntropy', 'tradingCost', 'netAlpha', 'cvarEs', 'tailAdjust', 'decayAlpha', 'transitionGate', 'ledoitWolf', 'deflatedSharpe'].every(k => typeof R[k] === 'function'));
ok('effBreadth', close(R.effectiveBreadth(g.n_tests, 0.3), g.effBreadth));
ok('enb', close(R.enbEntropy([4, 2, 1, 1, 0.5]), g.enb));
ok('tradingCost', close(R.tradingCost(3.0), g.tradingCost));
ok('dsr (erf tol)', Math.abs(R.deflatedSharpe(0.5, 250, 0, 3, g.n_tests) - g.dsr) < 2e-3);
ok('eb_tau2', close(R.ebTau2(g.rows.map(r => r.tot), g.rows.map(r => r.se)), g.ebTau2));
g.rows.forEach(function (row, i) {
  const cs = R.convictionSigma(row.base_sigma, row.z);
  ok('convSigma[' + i + ']', close(cs, row.convSigma), [cs, row.convSigma]);
  ok('lcb[' + i + ']', close(R.lcbScore(row.tot, row.se, g.k), row.lcb), [R.lcbScore(row.tot, row.se, g.k), row.lcb]);
  ok('score[' + i + ']', close(R.compositeRankScore(row.tot, row.z, row.base_sigma, g.k, g.n_tests, null, 1, row.se), row.score));
  ok('aFse[' + i + ']', close(R.alphaForecastSe(2.0, row.z, 0.0, 10.0, g.n_tests), row.aFse));
  ok('steinC[' + i + ']', close(R.steinShrink(row.tot, row.se, 3.0, 1.0), row.steinC));
  const eb = R.ebPosterior(row.tot, row.se, g.ebCenter, g.ebTau2);
  ok('ebMu[' + i + ']', close(eb.mu, row.ebMu));
  ok('ebSd[' + i + ']', close(eb.sd, row.ebSd));
  ok('ebW[' + i + ']', close(eb.w, row.ebW));
  ok('netAlpha[' + i + ']', close(R.netAlpha(row.tot, 1.0), row.netAlpha));
  ok('decayMu[' + i + ']', close(R.decayAlpha(row.tot, 5, 21), row.decayMu));
  ok('tailAdj[' + i + ']', close(R.tailAdjust(row.tot, 0.8, 0.1), row.tailAdj));
  ok('zAdj[' + i + ']', close(R.deflatedConviction(row.z, 150), row.zAdj));
  ok('gk[' + i + ']', close(R.grinoldKahn(0.08, row.base_sigma, row.z), row.gk));
});
console.log('\n' + (fails ? fails + ' FAILED' : 'ALL RANK PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
