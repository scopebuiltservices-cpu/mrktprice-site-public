#!/usr/bin/env python3
"""Planted-structure tests for tail_stability.py. Run: python3 test_tail_stability.py"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tail_stability import tail_panel, quantile_sorted, quantile_rank, effective_n

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# quantile sanity
ok("median of 1..9 is 5", quantile_sorted(list(range(1, 10)), 0.5) == 5.0)
ok("rank monotone", quantile_rank(100, 0.05) < quantile_rank(100, 0.95))
ok("effective_n halves-ish with overlap", effective_n(1000, 10) == 100.0)

random.seed(7)
# STABLE tail: 600 well-behaved standard-normal-ish studentized residuals, no recent shock.
stable = [random.gauss(0, 1) for _ in range(600)]
ps = tail_panel(stable, alpha=0.05, overlap=1, stable_tol=0.5)
ok("stable buffer -> stable=True", ps["stable"], ps.get("reason"))
ok("stable reports both tails + ranks", "lower" in ps["tails"] and ps["tails"]["lower"]["rank"] >= 1, ps["tails"]["lower"])
ok("stable nEff = n (overlap 1)", ps["nEff"] == 600, ps["nEff"])

# UNSTABLE lower tail: a benign body, then a big negative shock concentrated in the NEWEST 5%.
body = [random.gauss(0, 1) for _ in range(560)]
shock = [-8.0 - random.random() for _ in range(40)]      # newest 40 (~6.7%) are extreme downside
unstable = body + shock                                   # time-ordered oldest -> newest
pu = tail_panel(unstable, alpha=0.05, overlap=1, stable_tol=0.5)
ok("unstable buffer -> stable=False", not pu["stable"], pu)
ok("lower tail flagged unstable (drops shock -> quantile jumps)",
   not pu["tails"]["lower"]["stable"]
   and (pu["tails"]["lower"]["sensitivity"]["drop10pct"]["unstable"]
        or pu["tails"]["lower"]["sensitivity"]["drop5pct"]["unstable"]), pu["tails"]["lower"])
ok("lower-tail full quantile is deeply negative (shock present)", pu["tails"]["lower"]["quantile"] < -1.0,
   pu["tails"]["lower"]["quantile"])
# dropping the newest 5-10% should move the lower quantile UP toward the benign body (positive delta)
d10 = pu["tails"]["lower"]["sensitivity"]["drop10pct"]["delta"]
ok("dropping newest 10% moves lower quantile materially", d10 is not None and abs(d10) > 0.5, d10)

# overlap adjustment reflected
po = tail_panel(stable, alpha=0.05, overlap=10)
ok("overlap=10 -> nEff = n/10", po["nEff"] == 60.0, po["nEff"])

# tiny buffer guard
ok("tiny buffer -> not stable + reason", tail_panel([0.1, 0.2, 0.3], alpha=0.05)["stable"] is False)

print("\n" + ("ALL TAIL-STABILITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
