/* test_method_contracts.mjs — verifies the method-contract linter (tools/check-method-contracts.mjs):
   claims without prerequisites are flagged, disclaimers ("NOT Diebold-Li", "proxy") are NOT, and a dead
   `* 0` factor in a stat file is an ERROR. Run: node tools/market_map/test_method_contracts.mjs */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const LINT = fileURLToPath(new URL('../check-method-contracts.mjs', import.meta.url));
let F = 0;
const ok = (n, c) => { console.log((c ? '  PASS  ' : '  FAIL  ') + n); if (!c) F++; };

function run(dir) {
  try { return { out: execFileSync('node', [LINT], { cwd: dir, encoding: 'utf8' }), code: 0 }; }
  catch (e) { return { out: (e.stdout || '') + (e.stderr || ''), code: e.status || 1 }; }
}
function fixture(files) {
  const d = mkdtempSync(join(tmpdir(), 'mc-'));
  for (const [rel, body] of Object.entries(files)) {
    const p = join(d, rel); mkdirSync(join(p, '..'), { recursive: true }); writeFileSync(p, body);
  }
  return d;
}

// 1) CLAIM without prerequisites -> MRKT001 flagged
let d = fixture({ 'rate_real.py': '"""real-rate curve via the Diebold-Li level/slope/curvature betas."""\nL=(a+b+c)/3\n' });
let r = run(d);
ok('claiming Diebold-Li without lambda/loadings -> MRKT001', /MRKT001/.test(r.out));
rmSync(d, { recursive: true });

// 2) DISCLAIMER -> NOT flagged (negation-aware)
d = fixture({ 'rate_real.py': '"""5/10/30 level/slope/curvature PROXY (NOT Diebold-Li / Nelson-Siegel)."""\nL=(a+b+c)/3\n' });
r = run(d);
ok('disclaimer "NOT Diebold-Li ... PROXY" -> no MRKT001', !/MRKT001/.test(r.out));
ok('clean disclaimer file exits 0', r.code === 0);
rmSync(d, { recursive: true });

// 3) real DNS (has lambda + loadings) claiming Diebold-Li -> allowed
d = fixture({ 'dns.py': 'lambda_=0.06\ndef loadings(tau): return [1, (1-2.7**(-lambda_*tau))]  # Diebold-Li DNS\nbeta1=beta2=beta3=0\n' });
r = run(d);
ok('legit DNS with lambda+loadings -> no MRKT001', !/MRKT001/.test(r.out));
rmSync(d, { recursive: true });

// 4) risk-neutral without european -> MRKT004
d = fixture({ 'rn.py': '"""risk-neutral density via Breeden-Litzenberger second derivative."""\nf=1\n' });
r = run(d);
ok('risk-neutral without european/deamericanized -> MRKT004', /MRKT004/.test(r.out));
rmSync(d, { recursive: true });

// 5) dead `* A * 0` in a stat file -> MRKT009 ERROR + exit 1
d = fixture({ 'tools/market_map/pooled_rigor.py': 'def spa():\n    thr = mean * A * 0  # recentering\n    return thr\n' });
r = run(d);
ok('dead `* A * 0` in stat file -> MRKT009 ERROR', /MRKT009/.test(r.out) && /error/.test(r.out));
ok('dead-zero fails the gate (exit 1)', r.code === 1);
rmSync(d, { recursive: true });

// 6) legitimate `* 0.5` and waived `* 0` are NOT flagged
d = fixture({ 'tools/market_map/metrics.py': 'x = y * 0.5\nz = w * 0  # waive-dead-zero: intentional baseline\n' });
r = run(d);
ok('`* 0.5` not flagged and `# waive-dead-zero` respected', !/MRKT009/.test(r.out) && r.code === 0);
rmSync(d, { recursive: true });

// 7) fully clean tree -> OK message, exit 0
d = fixture({ 'a.py': 'def f(x):\n    return x * 2\n' });
r = run(d);
ok('clean tree -> OK exit 0', r.code === 0 && /OK/.test(r.out));
rmSync(d, { recursive: true });

console.log('\n' + (F ? F + ' FAILED' : 'ALL METHOD-CONTRACT TESTS PASSED'));
process.exit(F ? 1 : 0);
