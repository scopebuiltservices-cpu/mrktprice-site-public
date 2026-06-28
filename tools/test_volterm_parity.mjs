/* Exact Py<->JS parity: volterm_engine.js vs tools/volterm_golden.json. Run: node tools/test_volterm_parity.mjs */
import { createRequire } from 'module'; import fs from 'node:fs'; import path from 'node:path'; import url from 'node:url';
const require = createRequire(import.meta.url);
const here = path.dirname(url.fileURLToPath(import.meta.url));
const V = require('../volterm_engine.js');
const g = JSON.parse(fs.readFileSync(path.join(here,'volterm_golden.json'),'utf8'));
let fails=0; const ok=(n,c)=>{console.log((c?'  PASS  ':'  FAIL  ')+n); if(!c)fails++;};
const close=(a,b)=>(a==null&&b==null)||Math.abs(a-b)<=1e-9*(1+Math.abs(b));
ok('API',['hvTermStructure','varianceRatio','ewmaVol','blendedScale','sqrtBaseline','studentize'].every(k=>typeof V[k]==='function'));
const hv=V.hvTermStructure(g.returns,g.horizons), sq=V.sqrtBaseline(g.returns,g.horizons);
ok('hv',g.horizons.every(h=>close(hv[h],g.hv[h])));
ok('sqrt',g.horizons.every(h=>close(sq[h],g.sqrt[h])));
const v2=V.varianceRatio(g.returns,2),v5=V.varianceRatio(g.returns,5),v10=V.varianceRatio(g.returns,10);
ok('vr2',close(v2.vr,g.vr2.vr)&&close(v2.zRobust,g.vr2.zRobust)&&close(v2.ciLo,g.vr2.ciLo));
ok('vr5',close(v5.vr,g.vr5.vr)&&close(v5.z,g.vr5.z));
ok('vr10',close(v10.vr,g.vr10.vr)&&close(v10.ciHi,g.vr10.ciHi));
ok('ewma',close(V.ewmaVol(g.returns,0.94),g.ewma));
ok('blend',close(V.blendedScale({hv:0.1,ewma:0.2,garch:0.15},{hv:1,ewma:2,garch:1},5),g.blend));
console.log('\n'+(fails?fails+' FAILED':'ALL VOLTERM PARITY TESTS PASSED')); process.exit(fails?1:0);
