#!/usr/bin/env python3
"""Tests for portfolio_engine.py — planted structure + golden lock. Run: python3 test_portfolio_engine.py"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_engine as P

F = []
def ok(n, c):
    print(("  PASS  " if c else "  FAIL  ") + n)
    if not c: F.append(n)
def close(a, b, t=1e-9): return abs(a - b) <= t * (1 + abs(b))
def vclose(A, B, t=1e-9): return len(A) == len(B) and all(close(A[i], B[i], t) for i in range(len(A)))

# MV first-order condition: mu = lam * Sigma * w  (the optimum)
mu = [3.0, 1.0, -2.0, 4.0, 0.5]; beta = [1.1, 0.8, 1.4, 0.6, 1.0]; sidio = [2.0, 1.5, 2.5, 1.2, 1.8]; sm = 1.2; lam = 2.0
w = P.mv_weights_factor(mu, beta, sm, sidio, lam)
Sig = P.factor_cov(beta, sm, sidio)
Sw = [sum(Sig[i][j] * w[j] for j in range(len(w))) for i in range(len(w))]
ok("MV first-order condition mu = lam*Sigma*w", max(abs(mu[i] - lam * Sw[i]) for i in range(len(mu))) < 1e-7)
ok("higher mu -> higher weight", P.mv_weights_factor([2.0, 1.0], [1, 1], 1.0, [2, 2], 1.0)[0] > P.mv_weights_factor([2.0, 1.0], [1, 1], 1.0, [2, 2], 1.0)[1])
ok("lower idio vol -> higher weight", P.mv_weights_factor([1.0, 1.0], [1, 1], 1.0, [1, 3], 1.0)[0] > P.mv_weights_factor([1.0, 1.0], [1, 1], 1.0, [1, 3], 1.0)[1])
pj = P.project_long_only([2.0, -1.0, 5.0, 0.3, 1.2], w_max=0.35, budget=1.0)
ok("projection long-only", all(x >= -1e-12 for x in pj))
ok("projection box cap", all(x <= 0.35 + 1e-9 for x in pj))
ok("projection budget = 1", close(sum(pj), 1.0, 1e-6))
ok("turnover blend halfway", vclose(P.turnover_blend([0.5, 0.5], [0.1, 0.9], 0.5), [0.3, 0.7]))

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "portfolio_golden.json")
if not os.path.exists(GOLD):
    json.dump(P.gen_fixture(), open(GOLD, "w"), separators=(",", ":"))
g = json.load(open(GOLD))
gw = P.mv_weights_factor(g["mu"], g["beta"], g["sigma_m"], g["sigma_idio"], g["lam"])
ok("golden w", vclose(gw, g["w"]))
ok("golden proj", vclose(P.project_long_only(gw, 0.35, 1.0), g["proj"]))
ok("golden blend", vclose(P.turnover_blend(g["proj"], [0.2, 0.2, 0.2, 0.2, 0.2], 0.5), g["blend"]))

print("\n" + ("ALL PORTFOLIO-ENGINE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
