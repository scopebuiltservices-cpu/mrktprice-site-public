#!/usr/bin/env python3
"""Planted-structure tests for factor_eval (IC, HAC t, BH-FDR, sign-aware weights, deflated Sharpe).
Run: python3 test_factor_eval.py"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factor_eval as fe

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) Spearman IC: monotone -> +1, anti-monotone -> -1, shuffled noise ~ 0
ok("spearman_ic monotone = +1", abs(fe.spearman_ic([1,2,3,4,5],[10,20,30,40,50]) - 1.0) < 1e-9)
ok("spearman_ic anti-monotone = -1", abs(fe.spearman_ic([1,2,3,4,5],[9,7,5,3,1]) + 1.0) < 1e-9)
ok("spearman_ic robust to nonlinearity", fe.spearman_ic([1,2,3,4,5],[1,4,9,16,25]) > 0.99)  # monotone but convex

# 2) HAC mean-t: positive-mean IC series is significant; zero-mean noise is not; HAC widens SE under autocorr
random.seed(7)
pos = [0.08 + random.gauss(0, 0.03) for _ in range(80)]
st = fe.hac_mean_t(pos, maxlags=4)
ok("HAC: positive IC series significant (t>2)", st["t"] > 2.0, st)
noise = [random.gauss(0, 0.05) for _ in range(80)]
ok("HAC: zero-mean noise not significant (|t|<2)", abs(fe.hac_mean_t(noise, maxlags=4)["t"]) < 2.0)
# autocorrelated series: HAC SE should exceed the naive iid SE
ac = []; prev = 0.0
for _ in range(120):
    prev = 0.7 * prev + random.gauss(0, 0.05); ac.append(0.04 + prev)
hac = fe.hac_mean_t(ac, maxlags=10)["se"]; iid = (sum((x-sum(ac)/len(ac))**2 for x in ac)/len(ac)/len(ac))**0.5
ok("HAC SE > naive iid SE under autocorrelation", hac > iid, [hac, iid])

# 3) BH-FDR: rejects the small p's, controls the family; pure-noise p's mostly survive as non-rejections
rej, cut = fe.bh_fdr([0.001, 0.004, 0.02, 0.5, 0.7, 0.9], q=0.10)
ok("BH-FDR rejects the strong, keeps weak as non-sig", rej[0] and rej[1] and not rej[4] and not rej[5], rej)

# 4) factor_weights: a real +IC factor gets a positive weight, a -IC factor a negative weight,
#    a noise factor gets ~0 and fails the gate; weights normalized to sum(|w|)=1
random.seed(11)
hist = {
  "good":  [0.10 + random.gauss(0,0.03) for _ in range(80)],
  "short": [-0.09 + random.gauss(0,0.03) for _ in range(80)],
  "noise": [random.gauss(0,0.05) for _ in range(80)],
}
w = fe.factor_weights(hist, maxlags=4, q=0.10)
ok("good factor: positive weight + passes", w["good"]["weight"] > 0 and w["good"]["pass"], w["good"])
ok("short factor: negative weight + passes", w["short"]["weight"] < 0 and w["short"]["pass"], w["short"])
ok("noise factor: ~0 weight + fails gate", abs(w["noise"]["weight"]) < 1e-9 and not w["noise"]["pass"], w["noise"])
ssum = abs(w["good"]["weight"]) + abs(w["short"]["weight"]) + abs(w["noise"]["weight"])
ok("weights normalized (sum|w|=1)", abs(ssum - 1.0) < 1e-3, ssum)
ok("breadth = 2/3 significant", abs(w["_breadth"] - 0.667) < 0.01, w["_breadth"])

# 5) Deflated Sharpe: with the SAME observed SR, DSR falls as the honest trial count rises
d1 = fe.deflated_sharpe(0.12, 250, skew=-0.3, kurt=4.0, n_trials=1, sr_trials_std=0.10)
d50 = fe.deflated_sharpe(0.12, 250, skew=-0.3, kurt=4.0, n_trials=50, sr_trials_std=0.10)
ok("DSR decreases as trials rise (selection-bias haircut)", d50["dsr"] < d1["dsr"], [d1, d50])
ok("DSR is a probability in [0,1]", 0.0 <= d50["dsr"] <= 1.0, d50)
ok("sr0 (deflated benchmark) rises with trials", d50["sr0"] > d1["sr0"], [d1["sr0"], d50["sr0"]])

print("\n" + ("ALL FACTOR-EVAL TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
