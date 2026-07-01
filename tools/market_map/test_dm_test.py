#!/usr/bin/env python3
"""Planted tests for dm_test.py. Run: python3 test_dm_test.py"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dm_test import diebold_mariano, compare_methods, _t_two_sided_p

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# t p-value sanity (|t|~1.96, large df -> ~0.05)
ok("t p-value ~0.05 at t=1.96, df=100000", abs(_t_two_sided_p(1.96, 100000) - 0.05) < 0.005, _t_two_sided_p(1.96, 100000))
ok("t p-value ~1.0 at t=0", abs(_t_two_sided_p(0.0, 50) - 1.0) < 1e-6)

# --- planted: A clearly lower loss than B -> significant, better == 'A', DM negative ---
random.seed(1)
n = 250
la = [abs(random.gauss(0, 1)) for _ in range(n)]          # A losses ~ |N|, mean ~0.8
lb = [x + 0.5 + abs(random.gauss(0, 0.1)) for x in la]    # B always worse by ~0.5+
r = diebold_mariano(la, lb, h=1)
ok("A-better: significant", r["significant"], r)
ok("A-better: meanDiff < 0 (A lower loss)", r["meanDiff"] < 0, r["meanDiff"])
ok("A-better: DMstar < 0 and better == 'A'", r["DMstar"] < 0 and r["better"] == "A", r)

# --- equal accuracy: two noisy-but-exchangeable loss series -> NOT significant ---
random.seed(2)
base = [abs(random.gauss(0, 1)) for _ in range(300)]
lc = [x + random.gauss(0, 0.02) for x in base]
ld = [x + random.gauss(0, 0.02) for x in base]
r2 = diebold_mariano(lc, ld, h=1)
ok("equal accuracy: NOT significant", not r2["significant"], r2)
ok("equal accuracy: better == 'none'", r2["better"] == "none", r2)

# --- HLN horizon correction: larger h widens the Newey-West window, shrinks |DMstar| ---
random.seed(4)
overl = []
prev = 0.0
for _ in range(300):
    prev = 0.7 * prev + random.gauss(0, 1)      # serially correlated loss differential base
    overl.append(prev)
a = [1.0 + x for x in overl]
b = [1.05 + x for x in overl]                    # tiny persistent edge to A
r_h1 = diebold_mariano(a, b, h=1)
r_h5 = diebold_mariano(a, b, h=5)
ok("HLN: h=5 correction shrinks |DMstar| vs h=1", abs(r_h5["DMstar"]) < abs(r_h1["DMstar"]), {"h1": r_h1["DMstar"], "h5": r_h5["DMstar"]})

# --- compare_methods against a baseline ---
losses = {"sqrt_gauss": lb, "cand": la}          # cand (=A) beats baseline sqrt_gauss (=B)
cm = compare_methods(losses, baseline="sqrt_gauss", h=1)
ok("compare_methods: cand significantly beats baseline", cm["cand"]["significant"] and cm["cand"]["better"] == "A", cm["cand"])

# guard
ok("too few obs -> ok False", diebold_mariano([1, 2, 3], [1, 2, 3])["ok"] is False)

print("\n" + ("ALL DM-TEST TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
