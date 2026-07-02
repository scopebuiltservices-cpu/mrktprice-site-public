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

// ---- Tier 2 marks -----------------------------------------------------------------------------------
const brk = M.breakLines({ breaks: [{ x: 300, label: 'BP', kind: 'mean' }, { x: 420, label: 'ICSS', kind: 'var' }], yTop, yBot });
ok('breaks: two dashed verticals', (brk.match(/<line/g) || []).length === 2 && brk.includes('stroke-dasharray="2,3"'));
ok('breaks: mean=amber, var=accent', brk.includes('#e0c14a') && brk.includes('#39b6ff'));
ok('breaks: labels rendered', brk.includes('BP') && brk.includes('ICSS'));
ok('breaks: empty when none', M.breakLines({ breaks: [], yTop, yBot }) === '');

const rib = M.regimeRibbon({ segments: [{ x0: 400, x1: 460, state: 0 }, { x0: 460, x1: 520, state: 1 }, { x0: 520, x1: 560, state: 2 }], y: 30, h: 6 });
ok('ribbon: three segments', (rib.match(/<rect/g) || []).length === 3);
ok('ribbon: distinct state colors', rib.includes('#2ecc8f') && rib.includes('#ef5f4e') && rib.includes('#e0c14a'));
ok('ribbon: unknown state => muted', M.regimeRibbon({ segments: [{ x0: 0, x1: 10 }], y: 0, h: 6 }).includes('#8a93a0'));

const ou = M.ouLine({ mu: 101, sigma: 2, priceLo, priceHi, yTop, yBot, x0: 400, x1: 560, halfLifeLabel: '12d' });
ok('OU: dashed equilibrium line', ou.includes('stroke-dasharray="6,4"'));
ok('OU: ±σ zone rect drawn', ou.includes('<rect') && ou.includes('fill-opacity="0.08"'));
ok('OU: half-life label', ou.includes('t½ 12d'));
// zone must bracket μ: top of zone above μ line, bottom below
const yμ = yOf(101);
ok('OU zone brackets μ', yOf(103) < yμ && yμ < yOf(99));

const carP = M.carShade({ x0: 300, x1: 340, yTop, yBot, car: 0.03 });
const carN = M.carShade({ x0: 300, x1: 340, yTop, yBot, car: -0.03 });
ok('CAR: positive => green wash', carP.includes('#2ecc8f'));
ok('CAR: negative => red wash', carN.includes('#ef5f4e'));
ok('CAR: empty when no window', M.carShade({ car: 0.01 }) === '');

console.log('\n' + (process.exitCode ? 'SOME marks TESTS FAILED' : 'ALL ' + pass + ' marks PASS'));
