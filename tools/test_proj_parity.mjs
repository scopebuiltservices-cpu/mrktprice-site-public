/* Exact Py<->JS parity: proj_engine.js vs tools/proj_golden.json. Run: node tools/test_proj_parity.mjs */
import { createRequire } from 'module'; import fs from 'node:fs'; import path from 'node:path'; import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const P = require('../proj_engine.js');
const g = JSON.parse(fs.readFileSync(path.join(here,'proj_golden.json'),'utf8'));
let fails=0; const ok=(n,c)=>{console.log((c?'  PASS  ':'  FAIL  ')+n); if(!c)fails++;};
const close=(a,b)=>Math.abs(a-b)<=1e-6*(1+Math.abs(b));
ok('API',['cumulativeDecayMultiplier','buildFallbackProjection','expectedPathPrice','scoreAccuracy','skillVsNaive','probAboveNow'].every(k=>typeof P[k]==='function'));
ok('M21',close(P.cumulativeDecayMultiplier(21,3),g.M21));
const pj=P.buildFallbackProjection(199.50,205.80,0.022,21,3);
ok('proj.muH',close(pj.muH,g.proj.muH)); ok('proj.close',close(pj.projCloseFwdH,g.proj.projCloseFwdH));
ok('path10',close(P.expectedPathPrice(199.50,pj.muH,10,21,3),g.path10));
const sc=P.scoreAccuracy(203.90,205.80,0.022*Math.sqrt(21));
ok('score.sle',close(sc.signedLogError,g.score.signedLogError)); ok('score.sz',close(sc.signedZError,g.score.signedZError));
ok('prob',Math.abs(P.probAboveNow(0.05,0.10)-g.prob)<1e-3);
console.log('\n'+(fails?fails+' FAILED':'ALL PROJ PARITY TESTS PASSED')); process.exit(fails?1:0);
