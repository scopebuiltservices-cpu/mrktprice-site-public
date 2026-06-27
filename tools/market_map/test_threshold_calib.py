#!/usr/bin/env python3
"""Offline tests for threshold_calib: cutoff fit, out-of-sample walk-forward, default-degrade, DSR trials.
Run: python3 test_threshold_calib.py"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import threshold_calib as tc

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# Planted edge: forward return rises with the metric -> a high cutoff isolates positive, significant returns.
random.seed(4)
N = 400
vals = [random.uniform(0.5, 4.0) for _ in range(N)]
fwd = [0.01 * (v - 2.0) + random.gauss(0, 0.01) for v in vals]   # monotone in metric
fit = tc.fit_cutoff(vals, fwd, [1.5, 2.0, 2.5, 3.0], min_hits=20, side="ge")
ok("fit_cutoff returns a cutoff", fit is not None and fit["theta"] in (1.5, 2.0, 2.5, 3.0), fit)
ok("higher cutoff -> positive mean fwd", fit["mean"] > 0, fit)

wf = tc.walk_forward(vals, fwd, [1.5, 2.0, 2.5, 3.0], train_frac=0.6, min_hits=20, side="ge")
ok("walk_forward returns OOS result", wf is not None, wf)
ok("OOS t-stat positive on planted edge", wf["tOOS"] > 1.0, wf)
ok("trials = grid size (DSR honesty)", wf["trials"] == 4, wf)

# No-signal: forward return independent of metric -> degrade to the labeled default.
fwd0 = [random.gauss(0, 0.01) for _ in range(N)]
cal = tc.calibrate(
    {"RVOL": {"values": vals, "fwd": fwd, "grid": [1.5, 2.0, 2.5, 3.0], "side": "ge", "min_hits": 20},
     "Z": {"values": vals, "fwd": fwd0, "grid": [1.5, 2.0, 2.5], "side": "ge", "min_hits": 20}},
    defaults={"RVOL": 2.0, "Z": 2.0})
ok("RVOL calibrates to fitted (has edge)", cal["mode"]["RVOL"] == "fitted", cal["mode"])
ok("Z degrades to default (no edge)", cal["mode"]["Z"] == "default", cal["mode"])
ok("default keeps the literature value", cal["cutoffs"]["Z"] == 2.0, cal["cutoffs"])
ok("DSR trial count sums all grids tried", cal["trials"] == 4 + 3, cal["trials"])
ok("thin data -> walk_forward None", tc.walk_forward([1, 2, 3], [0.1, 0.2, 0.3], [1.5], min_hits=20) is None)

print("\n" + ("ALL THRESHOLD-CALIB TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
