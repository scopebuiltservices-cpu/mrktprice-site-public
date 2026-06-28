/* check-file-budget.mjs — SELF-ENFORCING size budget so no source file ever approaches the sandbox
   mount's ~1756-line read boundary again. This replaces the brittle "squeak under 1756" tactic with a
   principled, automated rule: every tracked .py / .mjs / .js source must stay UNDER its budget (default
   900 lines — roughly half the boundary, generous margin). A few known-large files (the build orchestrator)
   get an explicit ceiling that may ONLY be lowered over time (the ratchet), forcing the monolith to keep
   shrinking and blocking any regression that would re-cross the boundary.

   Run: node tools/check-file-budget.mjs   (exit 1 on any violation). Wired into verify_all.sh + CI + hook. */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const repo = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const DEFAULT_BUDGET = 900;
// Known-large files with explicit ceilings. RULE: these numbers may only DECREASE. Lower them as the
// orchestrator is further modularized; never raise them. (terminal.html is HTML, gated separately by
// check-scripts.mjs / check-external-js.mjs, so it is intentionally excluded here.)
const CEILINGS = {
  // RULE: ceilings may only DECREASE. Each is a known-large file still under the ~1756 boundary,
  // flagged as a future-extraction target. Lower as modularized; never raise.
  'tools/market_map/build_market_map.py': 1600,   // was ~1875; metrics.py extraction -> ~1573. Next: extract build()/real_universe().
  'tools/market_map/lineage.py': 1450,            // 1417; Phase-2 regime-lineage engine. Next: split estimators from orchestration.
};
const EXEMPT = new Set(['tools/engine_golden.json']);  // data/fixtures are not source

function walk(dir, out) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name === '.git' || e.name === '__pycache__') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(py|mjs|js)$/.test(e.name)) out.push(p);
  }
}

const files = [];
walk(path.join(repo, 'tools'), files);
for (const e of fs.readdirSync(repo)) { if (/\.(js|mjs)$/.test(e)) files.push(path.join(repo, e)); }

let fail = 0;
const rows = [];
for (const f of files) {
  const rel = path.relative(repo, f).split(path.sep).join('/');
  if (EXEMPT.has(rel)) continue;
  const n = fs.readFileSync(f, 'utf8').split('\n').length;
  const budget = CEILINGS[rel] ?? DEFAULT_BUDGET;
  rows.push({ rel, n, budget, over: n > budget });
  if (n > budget) { fail = 1; console.log(`  OVER  ${rel}: ${n} lines > budget ${budget}`); }
}

rows.sort((a, b) => b.n - a.n);
console.log('\nLargest source files:');
for (const r of rows.slice(0, 8)) {
  console.log(`  ${r.over ? 'XX' : 'ok'}  ${String(r.n).padStart(5)} / ${r.budget}  ${r.rel}`);
}
console.log('\n' + (fail
  ? 'FILE-BUDGET: VIOLATIONS ABOVE — split the file into a small module + import, do not raise the budget.'
  : `FILE-BUDGET: all ${rows.length} source files within budget (default ${DEFAULT_BUDGET}, boundary ~1756).`));
process.exit(fail);
