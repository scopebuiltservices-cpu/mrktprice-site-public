/* test_endpoint_bands.mjs — HEADLESS verification of endpoint_bands.js against a MOCK 2D canvas context that
 * records every op. This is the answer to "can't verify the visual result from here": we assert the GEOMETRY
 * (bracket counts, dashed vs solid, bootstrap-vs-parametric width ordering, in-bounds y, side placement) with
 * zero browser. Asserts: both bands draw two brackets; the bootstrap bracket is dashed and the parametric solid;
 * bootWider is reported correctly; a missing expA (or missing sub-band) is a clean no-op; y-coords honor the map. */
import assert from 'node:assert';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const EB = require('./endpoint_bands.js');

let pass = 0;
function ok(n, c, x) { if (c) { pass++; console.log('  PASS ' + n); } else { console.log('  FAIL ' + n + '  ' + (x ?? '')); process.exitCode = 1; } }

// mock context: records strokeStyle at each stroke(), dash state, and all line segments
function mockCtx() {
  const ops = [];
  let dash = [], stroke = null, path = [];
  return {
    ops, get _strokes() { return ops.filter(o => o.t === 'stroke'); },
    strokeStyle: null, fillStyle: null, lineWidth: 1, font: '',
    setLineDash(d) { dash = d.slice(); },
    beginPath() { path = []; },
    moveTo(x, y) { path.push(['m', x, y]); },
    lineTo(x, y) { path.push(['l', x, y]); },
    stroke() { ops.push({ t: 'stroke', color: this.strokeStyle, dash: dash.slice(), segs: path.slice() }); },
    fillText(s, x, y) { ops.push({ t: 'text', s, x, y }); },
  };
}

const yOf = p => 300 - (p - 90) / (110 - 90) * (300 - 40); // price 90..110 -> y 300..40 (higher price = smaller y)
const expA = { band: { lo: 98, hi: 104 }, bandBoot: { lo: 96, hi: 106 } }; // bootstrap wider (dependence/tails)

// 1) both bands present
let g = mockCtx();
let r = EB.draw(g, { x: 500, yOf, expA, label: true });
ok('both bands drawn', r.drawn === true);
ok('two stroke() calls (parametric + bootstrap)', g._strokes.length === 2, g._strokes.length);
const solid = g._strokes.find(s => s.dash.length === 0);
const dashed = g._strokes.find(s => s.dash.length > 0);
ok('parametric bracket is solid', !!solid && solid.color === '#9ab4e0');
ok('bootstrap bracket is dashed', !!dashed && dashed.color === '#39b6ff' && dashed.dash.join(',') === '3,2');
ok('bootWider reported true (bootstrap 96-106 vs param 98-104)', r.bootWider === true);
ok('parametric drawn LEFT of x, bootstrap RIGHT', solid.segs[0][1] < 500 && dashed.segs[0][1] >= 500, JSON.stringify([solid.segs[0][1], dashed.segs[0][1]]));
// y-mapping honored: top cap y == yOf(hi)
ok('parametric top-cap y == yOf(param.hi)', Math.abs(solid.segs[0][2] - yOf(104)) < 1e-9);
ok('bootstrap top-cap y == yOf(boot.hi)', Math.abs(dashed.segs[0][2] - yOf(106)) < 1e-9);
ok('label drawn', g.ops.some(o => o.t === 'text' && o.s === 'band'));

// 2) bootstrap NARROWER than parametric -> bootWider false
g = mockCtx();
r = EB.draw(g, { x: 500, yOf, expA: { band: { lo: 94, hi: 108 }, bandBoot: { lo: 98, hi: 104 } } });
ok('bootWider false when bootstrap tighter', r.bootWider === false);

// 3) accept {low,high} shape too
g = mockCtx();
r = EB.draw(g, { x: 300, yOf, expA: { band: { low: 99, high: 103 }, bandBoot: { low: 97, high: 105 } } });
ok('accepts {low,high} band shape', r.drawn === true && g._strokes.length === 2);

// 4) guards / no-ops
ok('no expA -> no-op', EB.draw(mockCtx(), { x: 1, yOf }).drawn === false);
ok('null ctx -> no-op', EB.draw(null, { x: 1, yOf, expA }).drawn === false);
g = mockCtx();
r = EB.draw(g, { x: 200, yOf, expA: { band: { lo: 99, hi: 101 } } }); // only parametric
ok('single band -> one bracket, bootWider null', r.drawn === true && g._strokes.length === 1 && r.bootWider === null);

console.log('\n' + (process.exitCode ? 'SOME endpoint_bands TESTS FAILED' : 'ALL ' + pass + ' endpoint_bands PASS'));
