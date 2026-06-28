/* check-duplication.mjs — SELF-POLICING "one canonical math library" gate (criterion #3).
   metrics.py is the single home for the canonical risk/return estimators. This fails CI if any of those
   names is (re)defined as a TOP-LEVEL function in another module, UNLESS that location is on the
   documented ALLOW list (an intentional, mathematically-distinct variant). It is the duplication analog
   of check-file-budget.mjs: it does not chase a count, it encodes the rule so divergent copies can't
   silently reappear. Run: node tools/check-duplication.mjs

   The ALLOW list captures the audit's nuance: some same-named functions are deliberately different
   conventions, not copy-paste drift. New entries require a reason, so adding one is a conscious decision. */
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const repo = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const DIR = path.join(repo, 'tools', 'market_map');
const HOME = 'metrics.py';

// canonical estimators that must live ONLY in metrics.py (the risk/return library + core stats)
const CANON = new Set([
  'sharpe', 'sortino', 'calmar', 'max_drawdown', 'cagr', 'downside_dev', 'skewness', 'kurtosis',
  'value_at_risk', 'cvar', 'ulcer_index', 'information_ratio', 'ewma_vol', 'spearman', 'hurst',
  'beta', 'pearson', 'zscores', 'winsorize', 'half_life', 'variance_ratio',
]);

// intentional, mathematically-distinct variants — each MUST carry a reason.
// Each entry is a deliberate, mathematically-distinct variant proven consistent in
// test_canonical_parity.py (where applicable). New entries require a reason — adding one is a choice.
const ALLOW = {
  'sharpe': {
    'composite_gate.py': 'annualized per-REBALANCE Sharpe; different signature (series, periods_per_year); == metrics.sharpe(.,rf=0,periods=P)',
    'pooled_rigor.py': 'per-OBSERVATION Sharpe (un-annualized) for deflated-Sharpe/PSR/MinTRL; == metrics.sharpe(.,rf=0,periods=1); returns None (not nan) on degenerate input',
  },
  'variance_ratio': {
    'engine_ref.py': 'Lo-MacKinlay VR on RETURNS mirroring engine.js for the golden-fixture parity; metrics.variance_ratio is VR on CLOSES (different input domain)',
  },
  'winsorize': {
    'data_quality.py': 'pre-fit hardening winsorize with a min-sample (>=5) floor for the IC/regression path; metrics.winsorize preserves None positions for the cross-section',
  },
  'pearson': {
    'signal_linkage.py': 'degenerate-safe (returns 0.0, not nan) for the IC/FDR pipeline; metrics.pearson returns nan on <3 / zero-variance',
  },
};

function topLevelDefs(file) {
  const names = [];
  const txt = fs.readFileSync(file, 'utf8');
  for (const line of txt.split('\n')) {
    const m = /^def\s+([A-Za-z_]\w*)\s*\(/.exec(line);   // top-level only (no leading indent)
    if (m) names.push(m[1]);
  }
  return names;
}

let fail = 0;
const flagged = [];
for (const f of fs.readdirSync(DIR)) {
  if (!f.endsWith('.py') || f === HOME || f.startsWith('test_')) continue;
  for (const name of topLevelDefs(path.join(DIR, f))) {
    if (!CANON.has(name)) continue;
    const allowed = ALLOW[name] && ALLOW[name][f];
    if (allowed) {
      flagged.push(`  ok    ${name} in ${f}  (allowed: ${allowed})`);
    } else {
      fail = 1;
      flagged.push(`  DUP   ${name} redefined in ${f} — canonical home is metrics.py. ` +
        `Import it (from metrics import ${name}) or, if intentionally different, add an ALLOW entry with a reason.`);
    }
  }
}

if (flagged.length) console.log(flagged.join('\n'));
console.log('\n' + (fail
  ? 'CHECK-DUPLICATION: divergent duplicate(s) above — consolidate to metrics.py or document the variant.'
  : 'CHECK-DUPLICATION: canonical estimators have a single source of truth (+ documented variants).'));
process.exit(fail);
