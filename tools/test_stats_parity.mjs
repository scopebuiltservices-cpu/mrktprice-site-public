/* Cross-language parity test (code-review H1): the dashboard's ADF + KPSS must agree with the Python
   reference tools/market_map/stats_ref.py on the golden fixture tools/stats_golden.json.

   It loads the ACTUAL shared engine.js (the same file terminal.html ships) and exercises its functions,
   so this is authoritative — not a drifting copy. engine.js is a classic UMD script, so we run it in a
   fresh Function scope and read globalThis.MrktEngine. Run: node tools/test_stats_parity.mjs */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const here = path.dirname(url.fileURLToPath(import.meta.url));
const repo = path.join(here, '..');
let fails = 0;
const ok = (n, c, d) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n + (c ? '' : '  -> ' + JSON.stringify(d))); if (!c) fails++; };

/* load the real engine.js into this process (it attaches to globalThis.MrktEngine) */
const engineCode = fs.readFileSync(path.join(repo, 'engine.js'), 'utf8');
new Function(engineCode)();          // classic script; UMD attaches to globalThis
const E = globalThis.MrktEngine;
ok('engine.js loaded + exposes MrktEngine', !!E && typeof E.adfTest === 'function' && typeof E.kpssTest === 'function');

const fix = JSON.parse(fs.readFileSync(path.join(repo, 'tools', 'stats_golden.json'), 'utf8'));
ok('golden fixture has cases', Array.isArray(fix.cases) && fix.cases.length >= 3, fix.cases && fix.cases.length);
for (const c of fix.cases) {
  const a = E.adfTest(c.series), k = E.kpssTest(c.series);
  ok(`[${c.name}] ADF tstat engine==Python`, Math.abs(a.tstat - c.adf.tstat) < 1e-6, [a.tstat, c.adf.tstat]);
  ok(`[${c.name}] ADF cv5 engine==Python`, Math.abs(a.cv5 - c.adf.cv5) < 1e-9, [a.cv5, c.adf.cv5]);
  ok(`[${c.name}] ADF lag + reject match`, a.lag === c.adf.lag && a.reject === c.adf.reject, [a.lag, a.reject, c.adf]);
  ok(`[${c.name}] KPSS eta engine==Python`, Math.abs(k.eta - c.kpss.eta) < 1e-6, [k.eta, c.kpss.eta]);
  ok(`[${c.name}] KPSS reject match`, k.reject === c.kpss.reject, [k.reject, c.kpss.reject]);
}

console.log('\n' + (fails ? (fails + ' FAILED') : 'ALL STATS PARITY TESTS PASSED — engine.js == Python reference'));
process.exit(fails ? 1 : 0);
