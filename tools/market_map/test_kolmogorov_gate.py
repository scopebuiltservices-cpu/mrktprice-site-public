#!/usr/bin/env python3
"""Planted-structure tests for kolmogorov_gate.py. Run: python3 test_kolmogorov_gate.py"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kolmogorov_gate import ks_two_sample, dual_gate, _probks

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- KS distance sanity ---
D, p, ne = ks_two_sample([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
ok("identical samples: D=0, p=1", D == 0.0 and p == 1.0, (D, p))
D2, p2, _ = ks_two_sample([1, 2, 3], [10, 11, 12])
ok("disjoint samples: D=1, p small", D2 == 1.0 and p2 < 0.2, (D2, p2))
ok("_probks monotone (bigger lambda -> smaller p)", _probks(0.5) > _probks(1.5) > _probks(2.5))

random.seed(7)
# --- STATIONARY: reference and current from the SAME N(0, 0.01) -> gate PASSES ---
stat = [random.gauss(0, 0.01) for _ in range(400)]
g = dual_gate(stat, ref_window=120, cur_window=60, alpha=0.05, min_n=30)
ok("stationary: passed + stationary + sufficient", g["passed"] and g["stationary"] and g["sufficient"], g)
ok("stationary: status admissible, high ksP", g["status"] == "admissible" and g["ksP"] >= 0.05, g)

# --- REGIME SHIFT (vol jump): recent 60 have 3x vol -> stationarity FAILS ---
shift = [random.gauss(0, 0.01) for _ in range(340)] + [random.gauss(0, 0.03) for _ in range(60)]
gs = dual_gate(shift, ref_window=120, cur_window=60, alpha=0.05, min_n=30)
ok("vol-jump: NOT passed, stationary False", (not gs["passed"]) and (not gs["stationary"]), gs)
ok("vol-jump: sufficient True (enough data), status regime-shifted", gs["sufficient"] and gs["status"] == "regime-shifted", gs)
ok("vol-jump: ksP < alpha", gs["ksP"] < 0.05, gs["ksP"])

# --- REGIME SHIFT (mean shift): recent 60 shifted up -> fails ---
mshift = [random.gauss(0, 0.01) for _ in range(340)] + [random.gauss(0.05, 0.01) for _ in range(60)]
gm = dual_gate(mshift, ref_window=120, cur_window=60, alpha=0.05, min_n=30)
ok("mean-shift: NOT passed", not gm["passed"], gm)

# --- THIN: too few observations -> sufficiency FAILS (never claims stationary on thin data) ---
gt = dual_gate([random.gauss(0, 0.01) for _ in range(40)], ref_window=120, cur_window=60, min_n=30)
ok("thin: not sufficient, not passed, status thin", (not gt["sufficient"]) and (not gt["passed"]) and gt["status"] == "thin", gt)

# --- grade in [0,1], higher when stationary ---
ok("grade in [0,1]", 0.0 <= g["grade"] <= 1.0 and 0.0 <= gs["grade"] <= 1.0)
ok("stationary grade > regime-shift grade", g["grade"] > gs["grade"], {"stat": g["grade"], "shift": gs["grade"]})

# --- power check: over many seeds, gate rarely false-alarms on stationary, usually catches shifts ---
random.seed(11)
fp = tp = 0
for _ in range(60):
    s = [random.gauss(0, 0.012) for _ in range(400)]
    if not dual_gate(s)["passed"]:
        fp += 1
    j = [random.gauss(0, 0.012) for _ in range(340)] + [random.gauss(0, 0.04) for _ in range(60)]
    if not dual_gate(j)["passed"]:
        tp += 1
ok("false-alarm rate on stationary < 20%", fp / 60 < 0.20, fp / 60)
ok("catches >= 80% of vol-jumps", tp / 60 >= 0.80, tp / 60)

print("\n" + ("ALL KOLMOGOROV-GATE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
