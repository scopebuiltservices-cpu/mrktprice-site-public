/* Exact Py<->JS parity: projlearn_engine.js vs tools/projlearn_golden.json. Run: node tools/test_projlearn_parity.mjs */
import { createRequire } from 'module'; import fs from 'node:fs'; import path from 'node:path'; import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const P = require('../projlearn_engine.js');
const g = JSON.parse(fs.readFileSync(path.join(here,'projlearn_golden.json'),'utf8'));
let fails=0; const ok=(n,c)=>{console.log((c?'  PASS  ':'  FAIL  ')+n); if(!c)fails++;};
const close=(a,b)=>Math.abs(a-b)<=1e-9*(1+Math.abs(b));
ok('API',['mincerZarnowitz','recalibrate','skillVsNaive','theilU2','learn','coverage'].every(k=>typeof P[k]==='function'));
const mz=P.mincerZarnowitz(g.pred,g.real);
ok('alpha',close(mz.alpha,g.mz.alpha)); ok('beta',close(mz.beta,g.mz.beta)); ok('r2',close(mz.r2,g.mz.r2));
ok('skill',close(P.skillVsNaive(g.pred,g.real),g.skill));
ok('u2',close(P.theilU2(g.pred,g.real),g.u2));
ok('recal',close(P.recalibrate(0.05,mz.alpha,mz.beta),g.recal));
const L=P.learn(g.pred,g.real);
ok('learn.wBeta',close(L.wBeta,g.learn.wBeta)); ok('learn.shrink',close(L.shrink,g.learn.shrink)); ok('learn.applied',L.applied===g.learn.applied);
console.log('\n'+(fails?fails+' FAILED':'ALL PROJLEARN PARITY TESTS PASSED')); process.exit(fails?1:0);
