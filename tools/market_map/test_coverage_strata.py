#!/usr/bin/env python3
"""Planted-structure tests for coverage_strata.py. Run: python3 test_coverage_strata.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coverage_strata import stratified_coverage, wilson_interval

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# Wilson sanity: 90/100 -> CI brackets 0.90, width reasonable
phat, lo, hi = wilson_interval(90, 100)
ok("wilson 90/100 phat=0.9", abs(phat - 0.90) < 1e-9)
ok("wilson CI brackets 0.9 and is inside (0,1)", lo < 0.90 < hi and 0 < lo and hi < 1, (lo, hi))
ok("wilson n=0 safe", wilson_interval(0, 0) == (None, 0.0, 1.0))

# Planted mis-coverage: 'up' well-calibrated at 90%, 'down' badly under-covered at ~60%.
recs = []
# 200 up records, 180 covered (90%)
for i in range(200):
    recs.append({"covered": i < 180, "horizon": 5, "sign": "up", "tod": "mid", "event": "calm",
                 "volRegime": "mid"})
# 200 down records, 120 covered (60%) -> should flag miscalibrated 'under'
for i in range(200):
    recs.append({"covered": i < 120, "horizon": 5, "sign": "down", "tod": "open", "event": "event",
                 "volRegime": "high"})

res = stratified_coverage(recs, nominal=0.90)
up = res["byDim"]["sign"]["up"]
down = res["byDim"]["sign"]["down"]
ok("up stratum ~0.90 not flagged", (not up["miscalibrated"]) and abs(up["coverage"] - 0.90) < 0.02, up)
ok("down stratum ~0.60 flagged UNDER", down["miscalibrated"] and down["direction"] == "under", down)
ok("marginal (0.75) also resolved as under", res["marginal"]["coverage"] == 0.75, res["marginal"])
ok("flags list contains the down/sign failure",
   any(f["dim"] == "sign" and f["level"] == "down" for f in res["flags"]), res["flags"])
ok("event=event stratum flagged too (same 200 under-covered)",
   res["byDim"]["event"]["event"]["miscalibrated"], res["byDim"]["event"])

# Thin-data guard: a 5-record stratum with 0 coverage must NOT be flagged (lowN)
thin = [{"covered": False, "horizon": 90, "sign": "up"} for _ in range(5)]
tres = stratified_coverage(thin, nominal=0.90, min_n=20)
ok("thin stratum not flagged (lowN)", not tres["byDim"]["sign"]["up"]["miscalibrated"]
   and tres["byDim"]["sign"]["up"]["lowN"], tres["byDim"]["sign"]["up"])

print("\n" + ("ALL COVERAGE-STRATA TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
