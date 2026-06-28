/* Parity/behavior test for pooled_rigor.js (mirror of pooled_rigor.py). Run: node tools/test_pooled_rigor.mjs */
import fs from 'fs'; import path from 'path'; import { fileURLToPath } from 'url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const code = fs.readFileSync(path.join(root, 'pooled_rigor.js'), 'utf8');
const w = {}; new Function('window', 'module', code)(w, { exports: {} });
const R = w.PooledRigor;
let F = [];
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) F.push(n); };

// PSR / MinTRL
ok('PSR rises with Sharpe', R.psr(0.20, 252) > R.psr(0.05, 252));
ok('PSR ~0.5 at SR==benchmark', Math.abs(R.psr(0.1, 252, 0, 3, 0.1) - 0.5) < 1e-6);
ok('MinTRL None when SR<=benchmark', R.minTRL(0.0) === null);
ok('MinTRL shrinks as SR grows', R.minTRL(0.30) < R.minTRL(0.10));

// effective breadth
const N = 6;
const ident = Array.from({ length: N }, (_, i) => Array.from({ length: N }, (_, j) => i === j ? 1 : 0));
const ones = Array.from({ length: N }, () => Array.from({ length: N }, () => 1));
ok('eff breadth identity == N', Math.abs(R.effectiveBreadth(ident) - N) < 1e-9);
ok('eff breadth ones == 1', Math.abs(R.effectiveBreadth(ones) - 1) < 1e-9);

// random-effects meta
ok('homogeneous I2 low', R.randomEffectsMeta([0.5, 0.52, 0.49, 0.51], [0.05, 0.05, 0.05, 0.05]).I2 < 30);
ok('heterogeneous I2 high', R.randomEffectsMeta([0.1, 0.9, 0.2, 1.2], [0.05, 0.05, 0.05, 0.05]).I2 > 70);

// mover decomp
const md = R.moverDecomp({ sMR: 0.5, sMom: 0.2, sSig: 0.1, sVol: 0 }, { sMR: 0.1, sMom: 0.2, sSig: 0.1, sVol: 0 });
ok('mover dnet = 0.35*0.4', Math.abs(md.dnet - 0.14) < 1e-9, md);

// two-way FE recovers planted slope (seeded)
let rng = (s => () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)(42);
const NT = 10, ND = 36, bt = 0.8, x = [], y = [], g = [], d = [];
const ge = {}, de = {}; for (let i = 0; i < NT; i++) ge[i] = rng() * 2 - 1; for (let t = 0; t < ND; t++) de[t] = rng() * 2 - 1;
for (let i = 0; i < NT; i++) for (let t = 0; t < ND; t++) { const xi = de[t] * 0.5 + (rng() * 2 - 1); x.push(xi); y.push(bt * xi + ge[i] + de[t] + (rng() - 0.5)); g.push(i); d.push(t); }
ok('two-way FE recovers slope', Math.abs(R.twoWayFE(x, y, g, d).beta - bt) < 0.12, R.twoWayFE(x, y, g, d));
ok('clustered SE positive + finite', (() => { const c = R.twoWayClusterSE(x, y, g, d); return c && c.se > 0 && isFinite(c.beta); })());

// bootstrap: good config -> lower PBO than noise; true outperformer -> smaller RC p than noise
let rr = (s => () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)(9);
const gauss = () => { let u = 0, v = 0; while (!u) u = rr(); while (!v) v = rr(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const T = 120, K = 8, Mg = [], Mn = [];
for (let t = 0; t < T; t++) { const row = []; for (let k = 0; k < K; k++) row.push(gauss()); const rg = row.slice(); rg[0] = gauss() + 0.4; Mg.push(rg); Mn.push(Array.from({ length: K }, () => gauss())); }
ok('PBO good < noise (or both low)', R.pboCSCV(Mg, 8).pbo <= R.pboCSCV(Mn, 8).pbo + 0.05, [R.pboCSCV(Mg, 8).pbo, R.pboCSCV(Mn, 8).pbo]);
const Dt = [], Dn = [];
for (let t = 0; t < 160; t++) { const b = []; for (let k = 0; k < 6; k++) b.push(gauss()); const bt2 = b.slice(); bt2[0] = gauss() + 0.25; Dt.push(bt2); Dn.push(Array.from({ length: 6 }, () => gauss())); }
ok('RC p(true) < p(noise)', R.realityCheck(Dt, 300).p < R.realityCheck(Dn, 300).p, [R.realityCheck(Dt, 300).p, R.realityCheck(Dn, 300).p]);

console.log('\n' + (F.length ? F.length + ' FAILED: ' + F.join(', ') : 'ALL POOLED-RIGOR JS TESTS PASSED'));
process.exit(F.length ? 1 : 0);
