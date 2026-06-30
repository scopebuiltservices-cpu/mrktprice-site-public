/* check-localstorage-auth.mjs — security lint for OWASP "don't store auth in web storage".
 *
 * Authentication tokens / session JWTs must not live in localStorage or sessionStorage: any script
 * running in the origin (XSS, a compromised CDN dep, a malicious extension) can read them. OWASP
 * recommends HttpOnly; Secure; SameSite cookies or a BFF (see AUTH_HARDENING.md).
 *
 * This lint scans committed *.html / *.js for web-storage AUTH patterns and reports each offender
 * (file + line). It is ADVISORY by default (exit 0) so it doesn't break the build before the auth
 * migration lands; run with --strict (exit 1 on any hit) to turn it into a hard gate AFTER you move
 * auth to cookies, so a regression can never silently reintroduce token-in-localStorage.
 *
 *   node tools/check-localstorage-auth.mjs            # advisory: list offenders, exit 0
 *   node tools/check-localstorage-auth.mjs --strict   # blocking: exit 1 if any offender remains
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const strict = process.argv.includes('--strict');
const root = process.cwd();
const SKIP = new Set(['.git', 'node_modules', '.build', '_site', 'reports']);

// (local|session)Storage used to set/get a credential-ish key: token, jwt, session, access/refresh, sb-/sb_, bearer
const RE = /(local|session)Storage\s*\.\s*(set|get)Item\s*\(\s*[`'"][^`'"]*(token|jwt|session|access[_-]?token|refresh|bearer|sb[-_])/i;

function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(html?|js|mjs)$/i.test(name)) out.push(p);
  }
  return out;
}

const hits = [];
for (const f of walk(root, [])) {
  const lines = readFileSync(f, 'utf8').split(/\r?\n/);
  lines.forEach((ln, i) => {
    if (RE.test(ln)) hits.push({ file: f.replace(root + '/', '').replace(root + '\\', ''), line: i + 1, text: ln.trim().slice(0, 120) });
  });
}

if (hits.length === 0) {
  console.log('check-localstorage-auth: OK — no auth tokens in web storage.');
  process.exit(0);
}

const tag = strict ? 'error' : 'warning';
console.log(`check-localstorage-auth: ${hits.length} web-storage AUTH pattern(s) found (${strict ? 'STRICT/blocking' : 'advisory'}):`);
for (const h of hits) {
  console.log(`::${tag} file=${h.file},line=${h.line}::auth token in web storage — move to HttpOnly cookie / BFF (see AUTH_HARDENING.md)`);
  console.log(`  ${h.file}:${h.line}  ${h.text}`);
}
console.log(strict
  ? '\nFAIL (--strict): remove auth tokens from web storage before this gate will pass.'
  : '\nAdvisory only. After completing AUTH_HARDENING.md, run with --strict to make this a blocking gate.');
process.exit(strict && hits.length ? 1 : 0);
