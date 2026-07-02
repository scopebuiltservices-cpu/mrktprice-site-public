/* test_marks.mjs — DOM-free property test for marks.js (the econometrician-mark SVG builders).
 * Asserts the invariants that make the marks HONEST, not just pretty:
 *   1) triple-band NESTING: sup-t half-width >= bootstrap >= conformal at the far horizon (a simultaneous
 *      band must never be drawn tighter than a pointwise band — that would understate path risk);
 *   2) cone geometry: every band renders (polygon fill for conformal, dashed boot, dotted sup-t, median);
 *   3) calibration chip color/label tracks the e-process LEVEL (ok/warn/kill) — the meta-mark can't lie
 *      about calibration state; kill => danger, warn => amber, ok => success;
 *   4) peak node draws a rotated diamond with UP (MFE) and DOWN (MAE) whiskers on the right sides;
 *   5) verdict glyph shows significance star only when Chow-Denning pJoint <= 0.10, else neutral RW.
 * Pure Node, no DOM — run by run-checks.sh via its test_*.mjs auto-discovery. */
import assert from 'node:assert';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = require('./marks.js');

let pass = 0;
function ok(name, cond, extra) { if (cond) { pass++; console.log('  PASS ' + name); } else { console.log('  FAIL ' + name + '  ' + (extra ?? '')); process.exitCode = 1; } }

// ---- build a synthetic widening triple-band cone in PRICE space -----------------------------------
const H = 8, p0 = 100, xs = [], median = [];
const conf = { up: [], lo: [] }, boot = { up: [], lo: [] }, supt = { up: [], lo: [] };
for (let h = 1; h <= H; h++) {
  xs.push(400 + h * 20);
  const s = Math.sqrt(h);                       // sqrt-time widening
  median.push(p0);
  conf.up.push(p0 + 1.0 * s); conf.lo.push(p0 - 1.0 * s);   // pointwise (narrowest)
  boot.up.push(p0 + 1.3 * s); boot.lo.push(p0 - 1.3 * s);   // dependence-aware bootstrap (wider)
  supt.up.push(p0 + 1.7 * s); supt.lo.push(p0 - 1.7 * s);   // simultaneous sup-t (widest)
}
const priceHi = 110, priceLo = 90, yTop = 40, yBot = 340;
const cone = M.coneBands({ xs, conf, boot, supt, median, priceLo, priceHi, yTop, yBot });

ok('cone: conformal fan is a filled polygon', cone.svg.includes('<polygon') && cone.svg.includes('fill-opacity="0.16"'));
ok('cone: bootstrap band is dashed', cone.svg.includes('stroke-dasharray="4,3"'));
ok('cone: sup-t band is dotted', cone.svg.includes('stroke-dasharray="1,4"'));
ok('cone: median line drawn', cone.svg.includes('stroke-width="1.5"'));
ok('cone NESTING sup-t >= boot >= conf (half-widths, px)',
   cone.half.supt >= cone.half.boot - 1e-9 && cone.half.boot >= cone.half.conf - 1e-9,
   JSON.stringify(cone.half));
ok('cone: half-widths strictly ordered (bands distinguishable)',
   cone.half.supt > cone.half.conf, JSON.stringify(cone.half));

// ---- calibration chip: color + label track the e-process level -------------------------------------
const chipOk = M.calibChip({ level: 'ok', eMax: 3.2, pAnytime: 0.31 });
const chipWarn = M.calibChip({ level: 'warn', eMax: 24.0, pAnytime: 0.04 });
const chipKill = M.calibChip({ level: 'kill', eMax: 140.0, pAnytime: 0.007 });
ok('chip ok => success color + ✓', chipOk.includes('#2ecc8f') && chipOk.includes('CALIB ✓'));
ok('chip warn => amber + DRIFT', chipWarn.includes('#e0c14a') && chipWarn.includes('CALIB DRIFT'));
ok('chip kill => danger + FAIL', chipKill.includes('#ef5f4e') && chipKill.includes('CALIB FAIL'));
ok('chip surfaces eMax + anytime-p', chipKill.includes('e=140') && chipKill.includes('p≤0.007'));
ok('chip null-safe (missing ce => quiet ok)', M.calibChip(null).includes('CALIB ✓'));

// ---- expected-peak node: diamond + up/down excursion whiskers ---------------------------------------
const pk = M.peakNode({ x: 560, priceLo, priceHi, yTop, yBot, peak: 102, mfe: 106, mae: 99, ttpLabel: '~9d' });
ok('peak: rotated diamond drawn', pk.includes('transform="rotate(45'));
ok('peak: MFE whisker in success color', pk.includes('#2ecc8f'));
ok('peak: MAE whisker in danger color', pk.includes('#ef5f4e'));
ok('peak: time-to-peak label', pk.includes('~9d'));
// MFE (106) is above peak (102) => smaller y; MAE (99) below => larger y. Verify ordering from the path.
const yOf = v => yBot - (v - priceLo) / (priceHi - priceLo) * (yBot - yTop);
ok('peak geometry: MFE above, MAE below', yOf(106) < yOf(102) && yOf(102) < yOf(99));

// ---- verdict glyph: significance-gated ---------------------------------------------------------------
ok('verdict: persist star when significant up', M.verdictGlyph({ vrStar: 1.4, pJoint: 0.03 }).includes('↑ PERSIST') && M.verdictGlyph({ vrStar: 1.4, pJoint: 0.03 }).includes('✱'));
ok('verdict: fade when significant down', M.verdictGlyph({ vrStar: 0.6, pJoint: 0.02 }).includes('↓ FADE'));
ok('verdict: neutral RW (no star) when insignificant', M.verdictGlyph({ vrStar: 1.2, pJoint: 0.4 }).includes('~ RW') && !M.verdictGlyph({ vrStar: 1.2, pJoint: 0.4 }).includes('✱'));
ok('verdict: empty when no data', M.verdictGlyph(null) === '');

console.log('\n' + (process.exitCode ? 'SOME marks TESTS FAILED' : 'ALL ' + pass + ' marks PASS'));
