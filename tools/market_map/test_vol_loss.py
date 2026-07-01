#!/usr/bin/env python3
"""Planted tests for vol_loss.py. Run: python3 test_vol_loss.py"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vol_loss as V

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# QLIKE = 0 exactly at the truth; > 0 otherwise
truth = [0.01, 0.02, 0.04, 0.03, 0.05] * 20
ok("QLIKE = 0 when forecast == realized", abs(V.qlike(truth, truth)) < 1e-12, V.qlike(truth, truth))
ok("QLIKE > 0 when forecast != realized", V.qlike([0.02] * len(truth), truth) > 0)
ok("MSE/MAE/RMSE = 0 at truth", V.mse(truth, truth) == 0 and V.mae(truth, truth) == 0 and V.rmse(truth, truth) == 0)

# every loss is minimized by the accurate forecaster vs a biased one (planted)
random.seed(3)
rv = [0.0004 * (1 + 0.5 * random.random()) for _ in range(400)]           # realized variances
good = [r * (1 + random.gauss(0, 0.05)) for r in rv]                       # tight, unbiased
bad = [r * (2.0 + random.gauss(0, 0.05)) for r in rv]                      # 2x biased high
sg, sb = V.score_vol(good, rv), V.score_vol(bad, rv)
for L in ("qlike", "mse", "rmse", "mae", "medae", "smape", "hmse"):
    ok(f"{L}: accurate < biased", sg[L] < sb[L], {"good": sg[L], "bad": sb[L]})

# proxy-robustness: QLIKE & MSE still rank good<bad when RV is a NOISY proxy of true variance
random.seed(7)
truevar = [0.0004] * 500
proxy = [tv * (0.5 + random.random()) for tv in truevar]                  # unbiased but very noisy proxy
gpred = [tv * 1.02 for tv in truevar]                                     # near-truth
bpred = [tv * 1.8 for tv in truevar]                                      # far
ok("QLIKE proxy-robust ranking holds", V.qlike(gpred, proxy) < V.qlike(bpred, proxy))
ok("MSE proxy-robust ranking holds", V.mse(gpred, proxy) < V.mse(bpred, proxy))

# guards
ok("empty/degenerate -> None", V.qlike([], []) is None and V.score_vol([-1, 0], [1, 1])["n"] == 0)
ok("SMAPE in [0,2]", 0 <= V.smape(bad, rv) <= 2)

print("\n" + ("ALL VOL-LOSS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
