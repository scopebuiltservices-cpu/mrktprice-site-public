#!/usr/bin/env node
/*
 * tools/check-scripts.mjs
 * ------------------------------------------------------------------
 * Extract every inline <script> block from the project's HTML files and
 * verify each one parses. This catches the class of bug where a truncated
 * or typo'd inline script throws a SyntaxError at load time and silently
 * kills every statement below it in the same block (exactly what happened
 * to the live-ticker IIFE).
 *
 * Zero dependencies — shells out to `node --check`.
 *
 * Usage:
 *   node tools/check-scripts.mjs                # every *.html in repo root
 *   node tools/check-scripts.mjs terminal.html  # specific file(s)
 *
 * Exit code 0 = all good, 1 = at least one block failed (or a file was
 * unreadable). Designed to be the command a CI job and a pre-commit hook run.
 */
import { readFileSync, writeFileSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const root = process.cwd();
const files = args.length
  ? args
  : readdirSync(root).filter((f) => f.toLowerCase().endsWith('.html'));

if (!files.length) {
  console.error('No HTML files to check.');
  process.exit(1);
}

const SCRIPT_RE = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;

// Only check scripts the browser would actually execute as JS.
// Skip external scripts (src=...) and non-JS types (application/json,
// text/template, x-tmpl, etc.).
function isExecutableJs(attrs) {
  if (/\bsrc\s*=/i.test(attrs)) return false;
  const m = attrs.match(/\btype\s*=\s*["']?([^"'\s>]+)/i);
  if (!m) return true; // no type attribute => classic JS
  const t = m[1].toLowerCase();
  return (
    t === 'text/javascript' ||
    t === 'application/javascript' ||
    t === 'module'
  );
}

const tmp = mkdtempSync(join(tmpdir(), 'sc-'));
let total = 0;
let failed = 0;

try {
  for (const file of files) {
    let html;
    try {
      html = readFileSync(file, 'utf8');
    } catch (e) {
      console.error(`! cannot read ${file}: ${e.message}`);
      failed++;
      continue;
    }

    let idxInFile = 0;
    let m;
    SCRIPT_RE.lastIndex = 0;
    while ((m = SCRIPT_RE.exec(html))) {
      const attrs = m[1];
      const body = m[2];
      if (!isExecutableJs(attrs)) continue;

      idxInFile++;
      total++;

      // HTML line number of the opening <script> tag, so failures are
      // easy to locate even though `node --check` reports a line within
      // the extracted block.
      const htmlLine = html.slice(0, m.index).split('\n').length;
      const isModule = /\btype\s*=\s*["']?module/i.test(attrs);
      const tmpFile = join(tmp, `block-${total}${isModule ? '.mjs' : '.js'}`);
      writeFileSync(tmpFile, body);

      try {
        execFileSync(process.execPath, ['--check', tmpFile], { stdio: 'pipe' });
        console.log(`  ok    ${file}  script #${idxInFile}  (opens at line ${htmlLine})`);
      } catch (e) {
        failed++;
        const out = (e.stderr || e.stdout || Buffer.from('')).toString().trim();
        const snippet = out
          .split('\n')
          .slice(0, 5)
          .map((s) => '        ' + s)
          .join('\n');
        console.error(
          `  FAIL  ${file}  script #${idxInFile}  (opens at line ${htmlLine})\n${snippet}`
        );
      }
    }
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

console.log(
  `\n${total - failed}/${total} inline script block(s) parsed across ${files.length} file(s).`
);
process.exit(failed ? 1 : 0);
