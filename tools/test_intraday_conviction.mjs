/* Parity + behavior test for intraday_conviction.js (mirror of intraday_conviction.py).
   Run: node tools/test_intraday_conviction.mjs */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');

// load the IIFE module and capture window.MrktIntradayConviction
const code = fs.readFileSync(path.join(root, 'intraday_conviction.js'), 'utf8');
const sandbox = { window: {}, module: { exports: {} } };
new Function('window', 'module', code)(sandbox.window, sandbox.module);
const IC = sandbox.window.MrktIntradayConviction || sandbox.module.exports;

let F = [];
function ok(n, c, d) { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) F.push(n); }

// long flip: all four core gates pass + confirmations
const m = { rvol: 2.34, z: 2.41, vwap_reclaim: true, obv_t: 2.27, mfi: 83, breakout_atr: 1.18 };
const r = IC.evaluate(m, null, 'long');
ok('long flip fires', r.flip === true, r.row);
ok('row val+cutoff', r.row.includes('RVOL 2.34≥2.00'), r.row);
ok('VWAP reclaim YES', r.row.includes('VWAP reclaim YES'), r.row);
ok('OBV t shown', r.row.includes('OBV slope t=+2.27≥2.00'), r.row);
ok('MFI + breakout', r.row.includes('MFI 83≥80') && r.row.includes('Breakout +1.18 ATR≥1.00'), r.row);

const r2 = IC.evaluate({ ...m, rvol: 1.4 }, null, 'long');
ok('blocked when RVOL < cutoff', r2.flip === false, r2.row);
ok('failed comparator still shown', r2.row.includes('RVOL 1.40≥2.00'), r2.row);

const rs = IC.evaluate({ rvol: 2.5, z: -2.6, vwap_reclaim: false, obv_t: -2.4 }, null, 'short');
ok('short flip fires (sign-reversed)', rs.flip === true, rs.row);
ok('short VWAP loss YES', rs.row.includes('VWAP loss YES'), rs.row);

// estimators
ok('sigmaTod = (P-VWAP)/sig', Math.abs(IC.sigmaTodDisplacement(102, 100, 1.0) - 2.0) < 1e-9);
ok('breakout/ATR = (P-level)/atr', Math.abs(IC.breakoutATR(105, 100, 2.5) - 2.0) < 1e-9);
ok('OBV t positive on rising line', IC.obvSlopeT([1, 2, 3, 4, 5, 6, 7, 8]) > 5);
ok('OBV t negative on falling line', IC.obvSlopeT([8, 7, 6, 5, 4, 3, 2, 1]) < -5);

console.log('\n' + (F.length ? F.length + ' FAILED: ' + F.join(', ') : 'ALL INTRADAY-CONVICTION JS TESTS PASSED'));
process.exit(F.length ? 1 : 0);
