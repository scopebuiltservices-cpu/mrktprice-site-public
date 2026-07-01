#!/usr/bin/env python3
"""Planted-structure tests for blend_sigma.py. Run: python3 test_blend_sigma.py"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blend_sigma import (bates_granger_weights, blend_variance, blended_sigma_daily4,
                         component_variances, weights_from_history)

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- convex-weight properties ---
w = bates_granger_weights({"hv": 4.0, "ewma": 1.0, "garch": 2.0})
ok("weights nonneg + sum to 1", all(v >= 0 for v in w.values()) and abs(sum(w.values()) - 1.0) < 1e-12, w)
ok("lower MSE -> higher weight (ewma best)", w["ewma"] > w["garch"] > w["hv"], w)
ok("degenerate MSE dropped", "x" not in bates_granger_weights({"x": 0.0, "hv": 1.0}))

# --- blend stays within the component range (convexity) ---
comps = {"hv": 1.0, "ewma": 4.0}
bv = blend_variance(comps, {"hv": 0.5, "ewma": 0.5})
ok("equal blend of {1,4} = 2.5", abs(bv - 2.5) < 1e-9, bv)
ok("blend within [min,max] of comps", 1.0 <= blend_variance(comps) <= 4.0)
ok("missing-arm renormalizes (only hv present)", abs(blend_variance({"hv": 3.0}, {"hv": .2, "ewma": .8}) - 3.0) < 1e-9)

# --- leakage-free weight estimation: GARCH-like arm tracks realized var far better -> dominates ---
random.seed(11)
hist = []
for _ in range(300):
    realized = 1.0 + 0.8 * random.random()          # true realized variance
    fc = {"good": realized + random.gauss(0, 0.05),  # tight tracker
          "bad": realized + random.gauss(0, 1.2)}    # noisy tracker
    hist.append((fc, realized))
wh = weights_from_history(hist, comps=("good", "bad"))
ok("history weights favor the accurate arm", wh["good"] > 0.8, wh)

# --- component_variances on a clustered (GARCH-ish) series returns real arms incl. garch ---
random.seed(3)
rets = []
vol = 0.01
for _ in range(400):
    vol = math.sqrt(1e-6 + 0.90 * vol * vol + 0.08 * (rets[-1] if rets else 0.0) ** 2)  # clustering
    rets.append(random.gauss(0, vol))
cv = component_variances(rets)
ok("hv + ewma present", "hv" in cv and "ewma" in cv, list(cv))
ok("garch arm computed (reuses lineage.garch11_fit)", "garch" in cv, list(cv))
ok("all component variances positive+finite", all(v > 0 and v == v for v in cv.values()), cv)

# --- rv arm injected from intraday realized variance ---
cv2 = component_variances(rets, rv_var=0.0004)
ok("rv arm injected when provided", cv2.get("rv") == 0.0004)

# --- blended_sigma_daily4: floor gamma respected, detail complete ---
sig, det = blended_sigma_daily4(rets, gamma=0.05)
ok("sigma >= gamma floor", sig >= 0.05, sig)
ok("detail carries components+weights+arms", set(("components", "weights", "blendVar", "arms")) <= set(det), list(det))
ok("weights used sum to ~1 over available arms", abs(sum(det["weights"].values()) - 1.0) < 1e-9, det["weights"])

# blended sigma is within the sqrt-range of the component sigmas (convex in variance space)
armvars = [cv[c] for c in cv]
ok("blended sigma within component sigma range", min(armvars) ** .5 - 1e-9 <= blended_sigma_daily4(rets)[0] <= max(armvars) ** .5 + 1e-9)

print("\n" + ("ALL BLEND-SIGMA TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
