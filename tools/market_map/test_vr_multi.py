"""Planted-structure test for metrics.variance_ratio_multi (Chow-Denning multiple variance-ratio test).

Asserts: the joint statistic detects persistence/mean-reversion when present, stays quiet on a random
walk, reads direction at the dominant horizon, and is ALWAYS more conservative than a single pointwise
test (the family-wise-error control the prioritization paper asked for)."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M

fail = 0


def ok(name, cond, extra=""):
    global fail
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        fail = 1


def trend(seed, n=400, a=0.6, vol=0.010):
    rng = random.Random(seed); c = [100.0]; e = 0.0
    for _ in range(n):
        e = a * e + (1 - a) * rng.gauss(0, 1); c.append(c[-1] * math.exp(vol * e))
    return c


def mr(seed, n=400, k=0.6, vol=0.012):
    rng = random.Random(seed); c = [100.0]; prev = 0.0
    for _ in range(n):
        z = rng.gauss(0, 1); step = vol * z - k * prev; prev = step; c.append(c[-1] * math.exp(step))
    return c


def rw(seed, n=400, vol=0.012):
    rng = random.Random(seed); c = [100.0]
    for _ in range(n):
        c.append(c[-1] * math.exp(rng.gauss(0, vol)))
    return c


tr = M.variance_ratio_multi(trend(1))
ok("trend: produced", tr is not None)
ok("trend: significant (pJoint<0.05)", tr and tr["pJoint"] < 0.05, tr and tr["pJoint"])
ok("trend: dominant VR>1 (persist)", tr and tr["vrStar"] > 1, tr and tr["vrStar"])
ok("trend: qStar in ladder", tr and tr["qStar"] in (2, 5, 10, 21), tr and tr["qStar"])
ok("trend: m horizons counted", tr and tr["m"] >= 3, tr and tr["m"])

mrr = M.variance_ratio_multi(mr(2))
ok("mr: significant", mrr and mrr["pJoint"] < 0.05, mrr and mrr["pJoint"])
ok("mr: dominant VR<1 (fade)", mrr and mrr["vrStar"] < 1, mrr and mrr["vrStar"])

r = M.variance_ratio_multi(rw(3))
ok("rw: not significant (pJoint>0.10)", r and r["pJoint"] > 0.10, r and r["pJoint"])

# joint is ALWAYS >= the pointwise two-sided p of the dominant statistic (FWER-conservative)
for lab, res in (("trend", tr), ("mr", mrr), ("rw", r)):
    mv = res["mv"]; phi = 0.5 * (1 + math.erf(mv / math.sqrt(2)))
    pointwise = 2.0 * (1.0 - phi)
    ok("%s: joint pJoint >= pointwise" % lab, res["pJoint"] >= pointwise - 1e-9, (res["pJoint"], pointwise))

ok("thin history -> None", M.variance_ratio_multi([100.0] * 20) is None)

print("\nALL variance_ratio_multi PASS" if not fail else "\nSOME variance_ratio_multi TESTS FAILED")
sys.exit(1 if fail else 0)
