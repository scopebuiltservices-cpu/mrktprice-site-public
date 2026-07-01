"""Planted-structure tests for volatility_arbiter.py — variance-space blend, reliability weighting,
VR overlay, additive event/jump variance, floor/cap, and the vr_lambda credibility helper."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import volatility_arbiter as VA

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


def close(a, b, tol=1e-9):
    return a is not None and abs(a - b) <= tol


C = VA.component

# equal components -> blended sigma == that sigma; equal weights
r = VA.blend([C("hv", 0.02, 1.0), C("ewma", 0.02, 1.0)])
ok("equal comps -> sigma unchanged", close(r["sigma"], 0.02))
ok("equal comps -> 50/50 weights", close(r["weights"]["hv"], 0.5) and close(r["weights"]["ewma"], 0.5))
ok("reliability reported", close(r["reliability"], 1.0))
ok("version tag", r["version"] == "vol_arbiter_v1")

# reliability weighting: a zero-reliability component is ignored
r2 = VA.blend([C("a", 0.01, 1.0), C("b", 0.03, 0.0)])
ok("zero-reliability comp dropped from weight", close(r2["sigma"], 0.01), r2["sigma"])

# base_weight tilts the blend: 3:1 on variances 1e-4 and 9e-4
r3 = VA.blend([C("a", 0.01, 1.0, base_weight=3.0), C("b", 0.03, 1.0, base_weight=1.0)])
ok("base-weight 3:1 -> sigma = sqrt(.75*1e-4 + .25*9e-4)", close(r3["sigma"], math.sqrt(0.0003)), r3["sigma"])

# VR overlay: lambda=0 leaves it unchanged; lambda=1 replaces with sigma_VR
r4 = VA.blend([C("hv", 0.02, 1.0)], sigma_vr=0.05, vr_reliability=0.0)
ok("VR lambda=0 -> unchanged", close(r4["sigma"], 0.02))
r5 = VA.blend([C("hv", 0.02, 1.0)], sigma_vr=0.05, vr_reliability=1.0)
ok("VR lambda=1 -> sigma == sigma_VR", close(r5["sigma"], 0.05), r5["sigma"])
ok("VR overlay weight recorded", close(r5["weights"]["vr_overlay"], 1.0))

# additive event + jump variance
r6 = VA.blend([C("hv", 0.02, 1.0)], event_sigma=0.01, jump_sigma=0.005)
ok("event+jump add in variance space", close(r6["sigma"], math.sqrt(0.02**2 + 0.01**2 + 0.005**2)), r6["sigma"])
ok("components echo event/jump", close(r6["components"]["event_sigma"], 0.01) and close(r6["components"]["jump_sigma"], 0.005))

# floor / cap
ok("cap enforced", close(VA.blend([C("x", 50.0, 1.0)], cap=10.0)["sigma"], 10.0))
ok("floor enforced", VA.blend([C("x", 1e-9, 1.0)], floor=1e-6)["sigma"] >= 1e-6)

# gating
try:
    VA.blend([C("x", 0.0, 1.0, available=True)])
    ok("no usable comps raises", False)
except ValueError:
    ok("no usable comps raises", True)
ok("unavailable comp skipped", close(VA.blend([C("a", 0.02, 1.0), C("b", 0.09, 1.0, available=False)])["sigma"], 0.02))

# all-zero reliability -> equal-weight fallback (still produces a sigma)
r7 = VA.blend([C("a", 0.02, 0.0), C("b", 0.04, 0.0)])
ok("all-zero reliability -> equal-weight fallback", close(r7["sigma"], math.sqrt(0.5 * 0.02**2 + 0.5 * 0.04**2)), r7["sigma"])

# vr_lambda credibility helper
ok("vr_lambda thin -> 0", VA.vr_lambda(2.0, 30, min_n=60) == 0.0)
ok("vr_lambda VR~1 -> 0 (nothing to correct)", VA.vr_lambda(1.0, 300, min_n=60) == 0.0)
ok("vr_lambda big-n + VR=2 -> kmax", close(VA.vr_lambda(2.0, 300, min_n=60, kmax=0.5), 0.5))
ok("vr_lambda bounded", 0.0 <= VA.vr_lambda(3.0, 120, min_n=60) <= 0.5)

print("\nALL volatility_arbiter PASS" if not fail else "\nSOME volatility_arbiter TESTS FAILED")
sys.exit(1 if fail else 0)
