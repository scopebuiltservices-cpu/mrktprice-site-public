#!/usr/bin/env python3
"""Canonical-parity test: proves the same-named estimators that live in MORE than one module are
either (a) the literal canonical metrics.py object, or (b) a DELIBERATE variant that agrees with the
canonical one under matched conventions. This is what lets check-duplication.mjs allowlist the variants
honestly — they are proven consistent, not silently divergent. Run: python3 test_canonical_parity.py"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
import composite_gate as CG
import pooled_rigor as PR
import factor_eval as FE
import signal_linkage as SL

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

def close(a, b, tol=1e-9):
    if a is None or b is None or a != a or b != b:
        return False
    return abs(a - b) <= tol * (1 + abs(b))

rets = [0.012, -0.008, 0.021, -0.015, 0.009, 0.003, -0.011, 0.017, -0.006, 0.014, 0.002, -0.019]

# --- sharpe: three variants are ONE core estimator (mu/sd, ddof=1) with different annualization ---
ok("composite_gate.sharpe(x,P) == metrics.sharpe(x,rf=0,periods=P)",
   close(CG.sharpe(rets, 12), M.sharpe(rets, rf=0.0, periods=12)), [CG.sharpe(rets, 12), M.sharpe(rets, rf=0.0, periods=12)])
ok("composite_gate.sharpe(x,1) == metrics.sharpe(x,periods=1)",
   close(CG.sharpe(rets, 1), M.sharpe(rets, rf=0.0, periods=1)))
ok("pooled_rigor.sharpe(x) == metrics.sharpe(x,rf=0,periods=1)  (per-observation, un-annualized)",
   close(PR.sharpe(rets), M.sharpe(rets, rf=0.0, periods=1)), [PR.sharpe(rets), M.sharpe(rets, rf=0.0, periods=1)])
# contract difference is intentional + documented: variants return None on degenerate input, metrics returns nan
ok("variants return None on n<2 (intentional contract; allowlisted in check-duplication)",
   CG.sharpe([0.01], 12) is None and PR.sharpe([0.01]) is None)

# --- spearman: signal_linkage now IS the canonical object; factor_eval.spearman_ic agrees with it ---
ok("signal_linkage.spearman is the canonical metrics.spearman", SL.spearman is M.spearman)
a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]; b = [2.0, 1.0, 4.0, 3.0, 6.0, 5.0]
ok("factor_eval.spearman_ic == metrics.spearman on aligned data",
   close(FE.spearman_ic(a, b), M.spearman(a, b)), [FE.spearman_ic(a, b), M.spearman(a, b)])
ok("metrics.spearman monotone-nonlinear == 1", close(M.spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 25]), 1.0))

print("\n" + ("ALL CANONICAL-PARITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
