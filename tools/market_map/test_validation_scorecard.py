#!/usr/bin/env python3
"""Planted-structure tests for validation_scorecard.py. Run: python3 test_validation_scorecard.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validation_scorecard import scorecard, tag_record
from maturity_protocol import MaturityProtocol

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# tag_record maps a ledger record into strata dims
tr = tag_record({"covered": True, "H": 5, "residual": -0.2, "sigma": 0.02, "issueT": 3,
                 "meta": {"event": "event"}}, vol_edges=(0.01, 0.03))
ok("tag: sign from residual (down)", tr["sign"] == "down", tr)
ok("tag: volRegime mid (0.02 in [0.01,0.03])", tr["volRegime"] == "mid", tr)
ok("tag: event carried from meta", tr["event"] == "event", tr)

# --- build a planted matured ledger: 'up' well-calibrated at 90%, 'down' under-covered at 60% ---
random.seed(9)
recs = []
def mk(sign, covered, H=5, sigma=0.02):
    # a band consistent with covered/uncovered so width + interval score are computable
    y = (0.01 if sign == "up" else -0.01)
    lo, hi = (-0.03, 0.03) if covered else (0.05, 0.06)  # if not covered, band excludes y
    return {"covered": covered, "H": H, "sigma": sigma, "residual": y, "y": y,
            "lower": lo, "upper": hi, "stud": (y - 0.0) / sigma, "sign": sign, "issueT": 0, "meta": {}}
for i in range(200):
    recs.append(mk("up", i < 180))      # 90% covered
for i in range(200):
    recs.append(mk("down", i < 120))    # 60% covered -> should flag

sc = scorecard(recs, nominal=0.90)
ok("byHorizon 5 present with coverage", "5" in sc["byHorizon"] and "coverage" in sc["byHorizon"]["5"], sc["byHorizon"])
ok("byHorizon carries width + interval score", "avgWidth" in sc["byHorizon"]["5"] and "meanIntervalScore" in sc["byHorizon"]["5"])
ok("marginal coverage = 0.75", sc["marginal"]["coverage"] == 0.75, sc["marginal"])
downcell = sc["stratified"]["byDim"]["sign"]["down"]
upcell = sc["stratified"]["byDim"]["sign"]["up"]
ok("stratified: down flagged miscalibrated UNDER", downcell["miscalibrated"] and downcell["direction"] == "under", downcell)
ok("stratified: up not flagged", not upcell["miscalibrated"], upcell)
ok("scorecard.flags surfaces the down/sign failure",
   any(f.get("dim") == "sign" and f.get("level") == "down" for f in sc["flags"]), sc["flags"])
ok("scorecard not ok when a stratum fails", sc["ok"] is False)

# --- tail stability wired in: plant an unstable lower tail via a recent shock in the studentized resids ---
shock = []
for i in range(560):
    shock.append(mk("up", True, H=10))
    shock[-1]["stud"] = random.gauss(0, 1)
for i in range(40):
    shock.append(mk("down", True, H=10))
    shock[-1]["stud"] = -8.0 - random.random()   # newest ~7% extreme downside
sc2 = scorecard(shock, nominal=0.90, embargo_overlap=10, stable_tol=0.5)
ok("tailStability computed for H=10", "10" in sc2["tailStability"], list(sc2["tailStability"]))
ok("tailStability flags the unstable tail", not sc2["tailStability"]["10"]["stable"], sc2["tailStability"]["10"].get("reason"))
ok("scorecard flags include tailUnstable", any(f.get("kind") == "tailUnstable" for f in sc2["flags"]), sc2["flags"])

# --- end-to-end from the real ledger: MaturityProtocol -> scorecard (no synthetic records) ---
mp = MaturityProtocol()
random.seed(1)
c = [100.0]
for _ in range(300):
    c.append(c[-1] * (1 + random.gauss(0, 0.01)))
Hh = 5
for t in range(0, len(c) - Hh):
    mp.issue(t, t, Hh, mu=0.0, sigma=0.01, lower=-0.02, upper=0.02, meta={"event": "calm"})
    realized = {fid: (c[fid + Hh] / c[fid] - 1.0) for fid in range(0, t + 1) if fid + Hh <= t}
    mp.observe(t, realized)
sc3 = scorecard(mp.matured_records(), nominal=0.90)
ok("end-to-end scorecard from live ledger has coverage", sc3["marginal"].get("n", 0) > 100 and "coverage" in sc3["marginal"], sc3["marginal"])

print("\n" + ("ALL VALIDATION-SCORECARD TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
