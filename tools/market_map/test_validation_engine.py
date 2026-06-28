#!/usr/bin/env python3
"""Tests for validation_engine.py — planted structure + golden lock. Run: python3 test_validation_engine.py"""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validation_engine as V

F = []
def ok(n, c):
    print(("  PASS  " if c else "  FAIL  ") + n)
    if not c: F.append(n)

# purged k-fold: partition test folds + embargo removal
sp = V.purged_kfold(100, 5, embargo=3)
ok("kfold count", len(sp) == 5)
ok("test folds partition [0,n)", sorted(t for _, te in sp for t in te) == list(range(100)))
tr, te = sp[2]
ok("train excludes test", not (set(tr) & set(te)))
lo, hi = min(te), max(te)
ok("embargo removes neighbors", all(not (lo - 3 <= j <= hi + 3) for j in tr))

# PBO: pure noise -> ~0.5; a genuine per-period edge -> low
random.seed(7); T, N = 120, 10
Mn = [[random.gauss(0, 1) for _ in range(N)] for _ in range(T)]
pbo_n = V.pbo_cscv(Mn, S=8)
ok("PBO(noise) ~ 0.5", 0.30 <= pbo_n <= 0.70)
Me = [[random.gauss(0, 1) + (0.8 if c == 0 else 0.0) for c in range(N)] for _ in range(T)]
ok("PBO(real edge) < PBO(noise)", V.pbo_cscv(Me, S=8) < pbo_n)

# gate
ok("gate deployable (high DSR, low PBO)", V.promotion_gate(0.99, 0.10)["deployable"])
ok("gate blocks low DSR", not V.promotion_gate(0.80, 0.10)["deployable"])
ok("gate blocks high PBO", not V.promotion_gate(0.99, 0.70)["deployable"])

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "validation_golden.json")
if not os.path.exists(GOLD):
    json.dump(V.gen_fixture(), open(GOLD, "w"), separators=(",", ":"))
g = json.load(open(GOLD))
ok("golden PBO", abs(V.pbo_cscv(g["M"], g["S"]) - g["pbo"]) < 1e-9)
ok("golden splits", [[tr, te] for tr, te in V.purged_kfold(20, 4, 2)] == g["splits"])
ok("golden gate ok", V.promotion_gate(0.99, 0.10)["deployable"] == g["gateOk"]["deployable"])

print("\n" + ("ALL VALIDATION-ENGINE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
