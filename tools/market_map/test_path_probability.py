#!/usr/bin/env python3
"""Monte-Carlo-validated tests for path_probability.py. Run: python3 test_path_probability.py

The MC oracle uses the Brownian-bridge max/min SAMPLER (the same bridge math lineage.py uses): a naive
step-sampled max undersamples crossings between steps (discrete-monitoring bias) and would understate the
true CONTINUOUS running max/touch. Bridge sampling recovers the continuous extrema with few steps, so it is
an unbiased oracle for the closed forms here.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import path_probability as P

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)


def mc_paths(s, m, n=60000, steps=32):
    """Continuous-extrema MC via the Brownian-bridge max/min sampler. Returns (end, runMax, runMin)."""
    random.seed(20260701)
    dt = 1.0 / steps
    sd = s * math.sqrt(dt)
    v = sd * sd
    md = m * dt
    out = []
    for _ in range(n):
        x = mx = mn = 0.0
        for _ in range(steps):
            a = x
            x = a + md + sd * random.gauss(0, 1)
            b = x
            root_hi = math.sqrt((b - a) * (b - a) - 2.0 * v * math.log(random.random()))
            root_lo = math.sqrt((b - a) * (b - a) - 2.0 * v * math.log(random.random()))
            seg_max = 0.5 * (a + b + root_hi)
            seg_min = 0.5 * (a + b - root_lo)
            if seg_max > mx:
                mx = seg_max
            if seg_min < mn:
                mn = seg_min
        out.append((x, mx, mn))
    return out


# ---------- driftless: closed forms vs bridge MC ----------
s = 0.20
paths = mc_paths(s, 0.0)
mc_touch = sum(1 for _, mx, _ in paths if mx >= 0.15) / len(paths)
ok("touch_up matches MC (driftless)", abs(P.touch_up(0.15, s) - mc_touch) < 0.008, {"cf": round(P.touch_up(0.15, s), 4), "mc": round(mc_touch, 4)})
mc_mfe = sum(mx for _, mx, _ in paths) / len(paths)
ok("E[MFE] closed form = s*sqrt(2/pi)", abs(P.expected_max_favorable(s) - s * math.sqrt(2 / math.pi)) < 1e-9)
ok("E[MFE] matches MC (driftless)", abs(P.expected_max_favorable(s) - mc_mfe) < 0.004, {"cf": round(P.expected_max_favorable(s), 4), "mc": round(mc_mfe, 4)})
mc_mae = sum(-mn for _, _, mn in paths) / len(paths)
ok("E[MAE] matches MC (driftless) and == MFE", abs(P.expected_max_adverse(s) - mc_mae) < 0.004 and abs(P.expected_max_adverse(s) - P.expected_max_favorable(s)) < 1e-9)
mxs = sorted(mx for _, mx, _ in paths)
mc_q90 = mxs[int(0.90 * len(mxs))]
ok("running_max q90 matches MC (driftless)", abs(P.running_max_quantile(0.90, s) - mc_q90) < 0.008, {"cf": round(P.running_max_quantile(0.90, s), 4), "mc": round(mc_q90, 4)})
b, k = 0.15, 0.05
num = sum(1 for x, mx, _ in paths if mx >= b and x >= k)
den = sum(1 for _, mx, _ in paths if mx >= b)
mc_cond = num / den if den else 0.0
ok("P(end>=k | touch b) matches MC (driftless)", abs(P.prob_end_above_given_touch_up(b, k, s) - mc_cond) < 0.015, {"cf": round(P.prob_end_above_given_touch_up(b, k, s), 4), "mc": round(mc_cond, 4)})
uncond = sum(1 for x, _, _ in paths if x >= k) / len(paths)
ok("touch-conditioning raises P(end>=k) vs unconditional", P.prob_end_above_given_touch_up(b, k, s) > uncond, {"cond": round(P.prob_end_above_given_touch_up(b, k, s), 3), "uncond": round(uncond, 3)})
ok("k above barrier: cond <= 1", P.prob_end_above_given_touch_up(0.10, 0.20, s) <= 1.0)

# ---------- with drift ----------
sd_, md_ = 0.20, 0.10
pd = mc_paths(sd_, md_)
mc_tu = sum(1 for _, mx, _ in pd if mx >= 0.15) / len(pd)
ok("touch_up matches MC (drift>0)", abs(P.touch_up(0.15, sd_, md_) - mc_tu) < 0.01, {"cf": round(P.touch_up(0.15, sd_, md_), 4), "mc": round(mc_tu, 4)})
mc_mfe_d = sum(mx for _, mx, _ in pd) / len(pd)
ok("E[MFE] matches MC (drift>0, numerical integ)", abs(P.expected_max_favorable(sd_, md_) - mc_mfe_d) < 0.006, {"cf": round(P.expected_max_favorable(sd_, md_), 4), "mc": round(mc_mfe_d, 4)})
mc_mae_d = sum(-mn for _, _, mn in pd) / len(pd)
ok("MFE > MAE under positive drift", P.expected_max_favorable(sd_, md_) > P.expected_max_adverse(sd_, md_) and abs(P.expected_max_adverse(sd_, md_) - mc_mae_d) < 0.006)

# ---------- price-space report ----------
rep = P.path_report(100.0, 0.02, 5, barrier_up=104.0, barrier_dn=97.0, level=102.0, drift_daily=0.0)
ok("path_report has MFE/MAE + touch + conditional", all(kk in rep for kk in ("mfePrice", "maePrice", "touchUp", "touchDn", "pEndAboveGivenTouchUp")), list(rep))
ok("path_report MFE price > S0 > MAE price", rep["mfePrice"] > 100.0 > rep["maePrice"], rep)
ok("touch probs in [0,1]", 0 <= rep["touchUp"] <= 1 and 0 <= rep["touchDn"] <= 1)

print("\n" + ("ALL PATH-PROBABILITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
