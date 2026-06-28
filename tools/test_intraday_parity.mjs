/* JS side of the intraday Py<->JS golden-fixture parity. Loads the REAL intraday_engine.js (CommonJS)
   and the committed tools/intraday_golden.json (produced by tools/market_map/test_intraday_parity.py),
   asserting intraday_engine.js reproduces the Python decimals to 1e-9 for the deterministic estimators.
   (block-bootstrap SE is excluded — Py/JS use different PRNGs; it keeps its planted-structure test.)
   Run: node tools/test_intraday_parity.mjs */
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const ie = require('../intraday_engine.js');
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };
const close = (a, b) => Math.abs(a - b) <= 1e-9 * (1 + Math.abs(b));

const g = JSON.parse(fs.readFileSync(path.join(here, 'intraday_golden.json'), 'utf8'));
const I = g.inputs, X = g.expected;
const se = ie.rollingSE(I.rets, I.mu);

ok('intraday engine exposes ewmaDrift/rollingSE/realizedQuarticity/signalQ',
  ['ewmaDrift', 'rollingSE', 'realizedQuarticity', 'signalQ'].every(k => typeof ie[k] === 'function'));
ok('ewmaDrift parity', close(ie.ewmaDrift(I.rets, I.lam), X.ewma_drift), [ie.ewmaDrift(I.rets, I.lam), X.ewma_drift]);
ok('rollingSE parity', close(se, X.rolling_se), [se, X.rolling_se]);
ok('realizedQuarticity parity', close(ie.realizedQuarticity(I.rets), X.realized_quarticity), [ie.realizedQuarticity(I.rets), X.realized_quarticity]);
ok('signalQ parity', close(ie.signalQ(I.mu, se), X.signal_q), [ie.signalQ(I.mu, se), X.signal_q]);

console.log('\n' + (fails ? fails + ' FAILED' : 'ALL INTRADAY PARITY (JS) TESTS PASSED'));
process.exit(fails ? 1 : 0);
