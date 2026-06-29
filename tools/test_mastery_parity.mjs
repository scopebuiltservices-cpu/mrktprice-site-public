/* Exact Py<->JS parity: mastery_engine.js vs tools/mastery_golden.json. Run: node tools/test_mastery_parity.mjs */
import { createRequire } from 'module'; import fs from 'node:fs'; import path from 'node:path'; import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const M = require('../mastery_engine.js');
const g = JSON.parse(fs.readFileSync(path.join(here,'mastery_golden.json'),'utf8'));
let fails=0; const ok=(n,c)=>{console.log((c?'  PASS  ':'  FAIL  ')+n); if(!c)fails++;};
const close=(a,b)=>Math.abs(a-b)<=1e-9*(1+Math.abs(b));
ok('API',['composite','classify','confidenceBand','twoConfirmation','reclassify'].every(k=>typeof M[k]==='function'));
ok('composite',close(M.composite(g.comp),g.compScore));
const ms=M.classify(g.comp,g.crit,{n:800,initialPass:true,delayedPass:true});
ok('mastery.tier',ms.tier===g.mastery.tier); ok('mastery.overall',close(ms.overall,g.mastery.overall)); ok('mastery.band',ms.band===g.mastery.band);
const bl=M.classify({concepts:0.99,procedure:0.99,reasoning:0.99,transfer:0.99,selfmon:0.99},{noLeak:0.5,coverage:0.95},{n:800});
ok('blocked.tier',bl.tier==='novice');
const pr=M.classify(g.comp,g.crit,{n:800,initialPass:true,delayedPass:false});
ok('prof.tier',pr.tier==='proficient');
ok('bands',M.confidenceBand(800)===g.band800 && M.confidenceBand(300)===g.band300 && M.confidenceBand(20)===g.band20);
ok('downgrade',M.reclassify([90,78,75])===g.downgrade);
console.log('\n'+(fails?fails+' FAILED':'ALL MASTERY PARITY TESTS PASSED')); process.exit(fails?1:0);
