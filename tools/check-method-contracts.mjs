/* check-method-contracts.mjs — METHOD-CONTRACT linter (audit R040 / MRKT001–010).
 *
 * Many of the platform's historical problems were "naming inflation": a label ("Diebold-Li",
 * "split-conformal", "risk-neutral", "zero curve") implying a mathematical contract the code doesn't meet,
 * or a dead literal factor (`* 0`, `* A * 0`) silently nullifying a statistical formula. This linter bans
 * those unless the minimum prerequisites are present, so the honesty work already done can't quietly regress.
 *
 * It is NEGATION-AWARE: a label used as a DISCLAIMER ("NOT Diebold-Li", "5/10/30 PROXY", "rather than
 * Nelson-Siegel") is allowed; only a label used as a CLAIM without its prerequisites is flagged. ADVISORY by
 * default (exit 0, warnings) so it doesn't break the build on a borderline docstring; run with --strict to
 * make it a blocking CI gate. Emits GitHub ::warning::/::error:: annotations. Pure Node, no deps.
 *
 *   node tools/check-method-contracts.mjs            # advisory
 *   node tools/check-method-contracts.mjs --strict   # blocking (exit 1 on any hit)
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const strict = process.argv.includes('--strict');
const root = process.cwd();
const SKIP = new Set(['.git', 'node_modules', '.build', '_site', 'reports']);
const NEG = /(not|n['’]t|isn|aren|rather than|instead of|proxy|≠|no longer|never claims?|deprecat)/i;

// A label is a CLAIM unless a negation/disclaimer word sits within ~48 chars on either side.
function claimsOf(text, label) {
  const re = new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  const hits = []; let m;
  while ((m = re.exec(text))) {
    const from = Math.max(0, m.index - 48), to = Math.min(text.length, m.index + m[0].length + 48);
    if (!NEG.test(text.slice(from, to))) hits.push(m.index);
  }
  return hits;
}
function lineOf(text, idx) { return text.slice(0, idx).split(/\r?\n/).length; }

// rule: {id, labels[], requireAny[] (regex the file must contain if a claim is present), why}
const RULES = [
  { id: 'MRKT001', labels: ['Diebold-Li', 'Diebold–Li', 'Nelson-Siegel', 'Nelson–Siegel', 'DNS'],
    requireAny: [/\blambda\b/i, /loadings?/i, /\bbeta1\b/i, /\bbeta2\b/i, /\bbeta3\b/i, /β1/],
    why: 'Diebold-Li/Nelson-Siegel/DNS require a decay parameter (lambda) + maturity loadings; a 3-point L/S/C summary is a PROXY, not DNS.' },
  { id: 'MRKT002', labels: ['split-conformal', 'regime×horizon conformal', 'regime x horizon conformal'],
    requireAny: [/matured/i, /purge/i, /embargo/i, /bucket[_ ]?id/i, /reg_q|byRegimeConformal/],
    why: 'split-conformal / regime×horizon conformal requires matured residuals + a calibration/test split (purge/embargo/bucket).' },
  { id: 'MRKT004', labels: ['risk-neutral', 'Breeden-Litzenberger', 'Breeden–Litzenberger'],
    requireAny: [/european/i, /deamericaniz|de-americaniz/i, /exercise[_ ]?style/i],
    why: 'risk-neutral / Breeden-Litzenberger on single-name chains needs European style or an explicit de-Americanization.' },
  { id: 'MRKT010', labels: ['zero curve', 'zero-curve'],
    requireAny: [/bootstrap/i, /discount[_ ]?factor/i, /ZeroCurve/],
    why: 'a "zero curve" must be bootstrapped to discount factors — raw constant-maturity par yields are not a zero curve.' },
];

// stat-critical files where a dead literal-zero factor is almost certainly a bug (the SPA `* A * 0` class).
const STAT_FILES = /tools\/market_map\/(pooled_rigor|factor_eval|metrics|composite_gate|rate_real|lineage|anti_deviation|drift_calib\d?|regime_ic|residualize_engine|beta_adjust)\.py$/;
const DEAD_ZERO = /\*\s*0(?![.\dxXeE_])/;   // "* 0" times a literal integer zero (allows *0.5, *0x, *0e-3)

function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name), st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(py|js|mjs|md|json)$/i.test(name)) out.push(p);
  }
  return out;
}

const files = walk(root, []);
const issues = [];   // {id, sev, file, line, msg}
for (const f of files) {
  const rel = f.replace(root + '/', '').replace(root + '\\', '').replace(/\\/g, '/');
  let text; try { text = readFileSync(f, 'utf8'); } catch (e) { continue; }

  for (const rule of RULES) {
    let claimed = false, firstIdx = -1;
    for (const lab of rule.labels) { const h = claimsOf(text, lab); if (h.length) { claimed = true; if (firstIdx < 0) firstIdx = h[0]; } }
    if (claimed && !rule.requireAny.some(re => re.test(text))) {
      issues.push({ id: rule.id, sev: 'WARN', file: rel, line: lineOf(text, firstIdx), msg: rule.why });
    }
  }

  // dead literal-zero factor in a statistical formula (skip comment lines)
  if (STAT_FILES.test(rel)) {
    text.split(/\r?\n/).forEach((ln, i) => {
      const code = ln.split('#')[0];
      if (DEAD_ZERO.test(code) && !/waive[- ]?dead-?zero/i.test(ln)) {
        issues.push({ id: 'MRKT009', sev: 'ERROR', file: rel, line: i + 1, msg: 'dead literal `* 0` factor in a statistical formula nullifies the term (the SPA `* A * 0` class). Remove it or add a `# waive-dead-zero` justification.' });
      }
    });
  }
}

if (!issues.length) { console.log('check-method-contracts: OK — no label overclaims or dead-zero factors.'); process.exit(0); }
const errors = issues.filter(i => i.sev === 'ERROR');
console.log(`check-method-contracts: ${issues.length} issue(s) (${errors.length} ERROR, ${issues.length - errors.length} WARN)${strict ? ' [STRICT]' : ' [advisory]'}`);
for (const it of issues) {
  const tag = (it.sev === 'ERROR' || strict) ? 'error' : 'warning';
  console.log(`::${tag} file=${it.file},line=${it.line}::[${it.id}] ${it.msg}`);
  console.log(`  ${it.sev}  ${it.file}:${it.line}  [${it.id}] ${it.msg}`);
}
// ERRORs always fail; WARNs fail only under --strict.
process.exit((errors.length || (strict && issues.length)) ? 1 : 0);
