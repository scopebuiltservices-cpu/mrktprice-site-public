/* check-external-js.mjs — syntax-gate the EXTERNAL <script src="*.js"> files.
 *
 * check-scripts.mjs validates only INLINE blocks and deliberately skips external src= files, so a broken
 * external module (engine.js, pooled_rigor.js, the panels, ...) would deploy silently and only fail at
 * runtime in the browser. This closes that gap: collect every LOCAL .js referenced by a <script src> in
 * the project's HTML, de-duplicate, and `node --check` each. Skips http/https/CDN URLs. Non-zero exit on
 * any failure so CI blocks the publish.
 *
 * Usage: node tools/check-external-js.mjs            (scan all root *.html)
 *        node tools/check-external-js.mjs a.html b.html
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const root = process.cwd();
const htmls = process.argv.slice(2).length
  ? process.argv.slice(2)
  : readdirSync(root).filter((f) => f.toLowerCase().endsWith('.html'));

const SRC_RE = /<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;
const seen = new Set();
for (const h of htmls) {
  let html = '';
  try { html = readFileSync(h, 'utf8'); } catch { continue; }
  let m;
  while ((m = SRC_RE.exec(html)) !== null) {
    let src = m[1].trim();
    if (/^https?:\/\//i.test(src) || src.startsWith('//')) continue;   // external CDN — not ours
    src = src.split('?')[0].split('#')[0];
    if (src.toLowerCase().endsWith('.js')) seen.add(src.replace(/^\.?\//, ''));
  }
}

let checked = 0, failed = 0, missing = 0;
const fails = [];
for (const f of [...seen].sort()) {
  if (!existsSync(f)) { missing++; console.error(`  MISS  ${f} (referenced but not found)`); continue; }
  try {
    execFileSync(process.execPath, ['--check', f], { stdio: 'pipe' });
    checked++; console.log(`  ok    ${f}`);
  } catch (e) {
    failed++; fails.push(f);
    console.error(`  FAIL  ${f}\n        ${String(e.stderr || e).split('\n').slice(0, 3).join('\n        ')}`);
  }
}

console.log(`\n${checked} external JS file(s) parsed${missing ? `, ${missing} missing` : ''}${failed ? `, ${failed} FAILED: ${fails.join(', ')}` : ''}.`);
process.exit(failed || missing ? 1 : 0);
