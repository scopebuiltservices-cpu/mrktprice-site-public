// Node tests for intraday_engine.js — mirrors tools/market_map/test_intraday.py against planted
// structure, and cross-checks the shared functions to the Python decimals. Run: node tools/test_intraday.mjs
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const ie = require('../intraday_engine.js');

let fails = 0;
function ok(name, cond, d) { console.log((cond ? '  PASS  ' : '  FAIL  ') + name + (cond ? '' : '  -> ' + d)); if (!cond) fails++; }

// robust stats (cross-check to Python)
ok('median odd', ie.median([3, 1, 2]) === 2);
ok('median even', Math.abs(ie.median([1, 2, 3, 4]) - 2.5) < 1e-9);
ok('mad of constant 0', ie.mad([5, 5, 5]) === 0);
ok('mad positive', ie.mad([-2, -1, 0, 1, 2]) > 0.8);

// normalizers + abnormality
let rng = mulberry32(1);
const hist0 = [];
for (let b = 0; b < 2000; b++) hist0.push({ bucket: b % 5, vol: 1e6 * Math.exp((b % 5) * 0.1 + gauss(rng) * 0.25), rv: 1e-5 * Math.exp(gauss(rng) * 0.4) });
const norms = ie.todNormalizers(hist0);
ok('normalizers cover buckets', Object.keys(norms).length === 5);
const spike = { bucket: 2, vol: 1e6 * Math.exp(0.2) * 6, rv: 1e-5 * 6 };
const ab = ie.abnormality(spike, norms);
ok('volume spike -> high zV', ab[0] > 3, ab[0]);
ok('RV spike -> high zRV', ab[1] > 3, ab[1]);
ok('gateA trips on dual spike', ie.gateA(ab[0], ab[1], 1.5, 1.5) === 1);
ok('gateA calm bar -> 0', ie.gateA(0.1, 0.1, 1.5, 1.5) === 0);

// consecutive trigger
ok('trigger at K=3', ie.consecutiveTrigger([0, 0, 1, 1, 1, 1], 3)[0] === 4);
ok('no trigger', ie.consecutiveTrigger([1, 0, 1, 0, 1, 0], 3)[0] === null);
ok('counter resets', ie.consecutiveTrigger([1, 1, 0, 1, 1, 1], 3)[0] === 5);

// log integration + bands + decision
const lp = ie.projectLogpath(2.0, [0.01, 0.01, 0.01]);
ok('cumulative log drift', Math.abs(lp[2] - 2.03) < 1e-12);
const [plo, phi] = ie.parametricBand([2, 2, 2], [0.02, 0.02, 0.02], [0, 0, 0], 1.0);
const w = phi.map((h, i) => h - plo[i]);
ok('band widens (sqrt-time)', w[0] < w[1] && w[1] < w[2]);
ok('band width = 2*sqrt(3)*0.02', Math.abs(w[2] - 2 * Math.sqrt(3) * 0.02) < 1e-9, w[2]);
const resid = { 0: Array.from({ length: 100 }, (_, i) => -0.05 + 0.0003 * i) };
const [clo, chi] = ie.conformalBand([2.0], resid, 0.9);
ok('conformal hi<center for negative residuals', chi[0] < 2.0, chi[0]);
ok('positive upper edge -> tradable long', (() => { const d = ie.decision(2.0, [2.05], [1.99], 0, 0, 1); return d.tradable && d.side === 'long'; })());
ok('edge<cost -> not tradable', !ie.decision(2.0, [2.001], [1.999], 0, 0.01, 1).tradable);
ok('hard gate G=0 vetoes trade', !ie.decision(2.0, [2.05], [1.99], 0, 0, 0).tradable);

// END-TO-END planted persistent spike + NO-LOOK-AHEAD
const hist2 = [];
for (let r = 0; r < 30; r++) for (let k = 0; k < 26; k++) hist2.push({ bucket: k, vol: 1e6 * Math.exp(gauss(rng) * 0.2), rv: 9e-6 * Math.exp(gauss(rng) * 0.4) });
function synth(n) { const bars = []; let p = 4.6; for (let k = 0; k < n; k++) { const hot = k >= 8; const r = (hot ? 0.004 : 0) + gauss(rng) * 0.003; const vol = 1e6 * Math.exp(gauss(rng) * 0.2) * (hot ? 6 : 1); const rv = 9e-6 * (hot ? 6 : 1) * Math.exp(gauss(rng) * 0.15); p += r; bars.push({ bucket: k, ret: r, rv: rv, vol: vol, p: p }); } return bars; }
const full = synth(26);
const out = ie.evaluate(full, hist2, { K: 3, warm: 4 });
ok('planted persistent spike triggers', out.triggered, out.T);
if (out.triggered) {
  const trunc = ie.evaluate(full.slice(0, out.T + 1), hist2, { K: 3, warm: 4 });
  ok('trigger index identical when future hidden (no look-ahead)', trunc.T === out.T, trunc.T + ' vs ' + out.T);
  ok('trigger at/after planted spike (k>=8)', out.T >= 8, out.T);
  ok('projection has H horizons', out.center.length === out.params.H);
  ok('center finite + positive', out.center.every((x) => x > 0 && isFinite(x)));
  ok('band brackets center at h0', out.hi[0] >= out.center[0] && out.center[0] >= out.lo[0]);
}

// coverage audit: 9/10 inside band -> 0.9 ; bias/sharpness/directional/baseline
const evs = [];
for (let i = 0; i < 10; i++) {
  const real = (i === 0) ? 1.15 : 1.0 + 0.01 * (i - 5);        // i=0 misses tight [0.95,1.05] but is inside RW [0.80,1.20]
  evs.push({ lo: 0.95, hi: 1.05, center: 1.0, realized: real, pT: 0.98, gatePass: i % 2 === 0,
             rwLo: 0.80, rwHi: 1.20 });
}
const a = ie.auditCoverage(evs, 0.9);
ok('coverage = 9/10', Math.abs(a.coverage - 0.9) < 1e-9, a.coverage);
ok('conditional (gated) coverage computed', a.condCoverageGated != null);
ok('random-walk baseline wider -> covers all', a.rwBaselineCoverage === 1.0, a.rwBaselineCoverage);
ok('directional accuracy in [0,1]', a.directionalAccuracy >= 0 && a.directionalAccuracy <= 1);
ok('avg band width = 0.10', Math.abs(a.avgBandWidth - 0.10) < 1e-9, a.avgBandWidth);
ok('empty events -> null', ie.auditCoverage([], 0.9) === null);

console.log('\n' + (fails ? (fails + ' FAILED') : 'ALL INTRADAY JS TESTS PASSED'));
process.exit(fails ? 1 : 0);

// --- deterministic gaussian (Box-Muller on mulberry32) for reproducible planted data ---
function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function gauss(r) { let u = 0, v = 0; while (u === 0) u = r(); while (v === 0) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
