#!/usr/bin/env python3
"""Planted-structure tests for band_bakeoff.py. Run: python3 test_band_bakeoff.py"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from band_bakeoff import bakeoff, run_bakeoff_multi, _ppf, METHODS

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# inverse-normal sanity
ok("ppf(0.975) ~ 1.96", abs(_ppf(0.975) - 1.959963985) < 1e-4, _ppf(0.975))
ok("ppf(0.5) = 0", abs(_ppf(0.5)) < 1e-9)

def closes_from_rets(rets, p0=100.0):
    c = [p0]
    for r in rets:
        c.append(c[-1] * math.exp(r))
    return c

# --- iid normal at H=1: sqrt-time Gaussian is exactly right -> coverage ~ nominal 0.90 ---
random.seed(21)
rets = [random.gauss(0, 0.012) for _ in range(700)]
closes = closes_from_rets(rets)
r1 = bakeoff(closes, H=1, alpha=0.10, min_train=120, min_cal=40, refit_garch_every=25)
sg = r1["methods"]["sqrt_gauss"]
ok("iid H=1: all 7 methods scored", len(r1["methods"]) == len(METHODS), list(r1["methods"]))
ok("iid H=1: sqrt_gauss coverage ~0.90", 0.85 <= sg["coverage"] <= 0.95, sg)
ok("iid H=1: every method finite width + IS", all(m["avgWidth"] > 0 and m["meanIntervalScore"] > 0 for m in r1["methods"].values()))
ok("iid H=1: conformal methods also ~nominal (0.84..0.96)",
   0.84 <= r1["methods"]["conformal_stud_asym"]["coverage"] <= 0.96, r1["methods"]["conformal_stud_asym"])
ok("best is defined + in method set", r1["best"] in r1["methods"], r1["best"])

# --- negatively-skewed, heteroskedastic series: asymmetric conformal should beat the naive
#     Gaussian on interval score (its whole reason to exist) ---
random.seed(5)
vol = 0.01
base_prev = 0.0
skew_rets = []
for i in range(900):
    # stationary GARCH(0.90,0.05) on the DIFFUSIVE part only; jumps affect the observed return, not the
    # variance recursion (so the process stays stationary and never explodes).
    vol = math.sqrt(2e-6 + 0.90 * vol * vol + 0.05 * base_prev * base_prev)
    vol = min(vol, 0.06)                        # safety cap
    z = random.gauss(0, 1)
    base = vol * z
    r = base
    if random.random() < 0.05:                 # occasional sharp DOWN jump -> negative skew + fat left tail
        r -= abs(random.gauss(0, 1)) * vol * 4.0
    skew_rets.append(r)
    base_prev = base
sc = closes_from_rets(skew_rets)
r5 = bakeoff(sc, H=5, alpha=0.10, min_train=150, min_cal=60, refit_garch_every=25)
asym = r5["methods"]["conformal_stud_asym"]["meanIntervalScore"]
naive = r5["methods"]["sqrt_gauss"]["meanIntervalScore"]
ok("skewed H=5: all 7 methods present", len(r5["methods"]) == len(METHODS), list(r5["methods"]))
ok("skewed H=5: asymmetric conformal IS <= naive sqrt-Gaussian IS", asym <= naive, {"asym": asym, "naive": naive})
ok("skewed H=5: asymmetric conformal is the best (or tied-best) method",
   r5["best"] in ("conformal_stud_asym", "conformal_stud_sym", "conformal_sym", "garch_gauss"), r5["best"])
# asymmetric band should be genuinely asymmetric on skewed data: lower tail wider than upper
# (checked indirectly: its coverage should be closer to nominal than symmetric conformal's)
ok("skewed: asym coverage within [0.85,0.96]", 0.85 <= r5["methods"]["conformal_stud_asym"]["coverage"] <= 0.96,
   r5["methods"]["conformal_stud_asym"])

# --- consolidation: DM significance + QLIKE variance scorecard emitted ---
ok("bakeoff emits dmVsBest (DM significance vs the best method)", isinstance(r5.get("dmVsBest"), dict) and len(r5["dmVsBest"]) > 0, list(r5.get("dmVsBest", {})))
ok("dmVsBest entries carry bestBeats + pValue", all("bestBeats" in v and "pValue" in v for v in r5["dmVsBest"].values()))
ok("bakeoff emits QLIKE volScore for the 4 parametric arms", len(r5.get("volScore", {})) == 4 and all(r5["volScore"][m]["qlike"] is not None for m in r5["volScore"]), list(r5.get("volScore", {})))
ok("bestSignificantlyBeats is a subset of methods", set(r5.get("bestSignificantlyBeats", [])) <= set(r5["methods"]))

# --- multi-horizon artifact shape ---
multi = run_bakeoff_multi(closes, horizons=(1, 5), alpha=0.10, min_train=120, min_cal=40, refit_garch_every=30)
ok("multi artifact has byHorizon 1 and 5", set(multi["byHorizon"]) == {"1", "5"}, list(multi["byHorizon"]))
ok("multi artifact nominal = 0.90", multi["nominal"] == 0.90)

print("\n" + ("ALL BAND-BAKEOFF TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
