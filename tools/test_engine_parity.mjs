/* Exact Py<->JS parity for engine.js's deterministic estimators (EMA, rolling realized vol, OU AR(1),
   Lo-MacKinlay variance ratio). Loads the REAL engine.js (globalThis.MrktEngine) and the committed
   golden fixture tools/engine_golden.json (produced by tools/market_map/engine_ref.py). Asserts engine.js
   reproduces the Python decimals to 1e-9 — closing the gap that these estimators previously only had
   planted-structure checks, not cross-language value parity. Run: node tools/test_engine_parity.mjs */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
const here = path.dirname(url.fileURLToPath(import.meta.url));
const repo = path.join(here, '..');
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };

new Function(fs.readFileSync(path.join(repo, 'engine.js'), 'utf8'))();
const E = globalThis.MrktEngine;
const g = JSON.parse(fs.readFileSync(path.join(here, 'engine_golden.json'), 'utf8'));
const I = g.inputs, X = g.expected;
const TOL = 1e-9;
const close = (a, b) => Math.abs(a - b) <= TOL * (1 + Math.abs(b));
const arrClose = (a, b) => Array.isArray(a) && a.length === b.length && a.every((v, i) => close(v, b[i]));

ok('engine exposes ema/hvRollSeries/ouFit/_varianceRatio',
  ['ema', 'hvRollSeries', 'ouFit', '_varianceRatio'].every(k => typeof E[k] === 'function'));

// EMA
ok('ema parity (engine.js == python decimals)', arrClose(E.ema(I.ema_c, I.ema_N), X.ema), 'ema mismatch');
// rolling realized vol
ok('hvRollSeries parity', arrClose(E.hvRollSeries(I.hv_r, I.hv_w), X.hv), 'hv mismatch');
// OU
const ou = E.ouFit(I.ou_x);
['phi', 'sePhi', 'theta', 'mu', 'muPrice', 'halfLife', 'sigmaX2', 'z', 'last'].forEach(k => {
  ok('ouFit.' + k + ' parity', close(ou[k], X.ou[k]), [k, ou[k], X.ou[k]]);
});
ok('ouFit.meanRev parity', ou.meanRev === X.ou.meanRev, [ou.meanRev, X.ou.meanRev]);
// variance ratio
const vr = E._varianceRatio(I.vr_r, I.vr_q);
ok('varianceRatio.vr parity', close(vr.vr, X.vr.vr), [vr.vr, X.vr.vr]);
ok('varianceRatio.z parity', close(vr.z, X.vr.z), [vr.z, X.vr.z]);

console.log('\n' + (fails ? fails + ' FAILED' : 'ALL ENGINE PARITY TESTS PASSED'));
process.exit(fails ? 1 : 0);
