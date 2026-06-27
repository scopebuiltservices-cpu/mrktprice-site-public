#!/usr/bin/env python3
"""Offline tests for rate_real: L/S/C identity, OLS duration betas recover planted sensitivity, classify.
Run: python3 test_rate_real.py"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_real as rr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) L/S/C identities
v = rr.lsc(2.0, 2.5, 3.0)
ok("level = mean(5,10,30)", abs(v["L"] - 2.5) < 1e-9, v)
ok("slope = 30y - 5y", abs(v["S"] - 1.0) < 1e-9, v)
ok("curvature = 2*10 - 5 - 30", abs(v["C"] - 0.0) < 1e-9, v)

# 2) duration betas recover a planted long-duration name: r = 0.4*rmkt - 1.5*dL + noise (bL<0)
random.seed(3)
N = 160; rmkt = [random.gauss(0, 0.01) for _ in range(N)]
dL = [random.gauss(0, 0.03) for _ in range(N)]; dS = [random.gauss(0, 0.02) for _ in range(N)]; dC = [random.gauss(0, 0.02) for _ in range(N)]
rets = [0.4 * rmkt[i] - 1.5 * dL[i] + random.gauss(0, 0.004) for i in range(N)]
d = rr.duration_betas(rets, rmkt, dL, dS, dC)
ok("recovers bMKT ~ 0.4", abs(d["bMKT"] - 0.4) < 0.15, d)
ok("recovers bL ~ -1.5 (negative)", d["bL"] < -1.0, d)
ok("bL is significant (|tL|>2)", abs(d["tL"]) > 2.0, d)
ok("classified long-duration", rr.classify(d) == "long-duration (rate-down beneficiary)", rr.classify(d))

# 3) anti-duration (bL>0 significant) and rate-agnostic (no rate loading)
rets2 = [0.3 * rmkt[i] + 1.4 * dL[i] + random.gauss(0, 0.004) for i in range(N)]
ok("classified anti-duration", rr.classify(rr.duration_betas(rets2, rmkt, dL, dS, dC)) == "anti-duration (rate-up beneficiary)")
rets3 = [0.5 * rmkt[i] + random.gauss(0, 0.01) for i in range(N)]
# pure-noise rate betas can clear |t|>2 ~14% of the time (3 coeffs); use the conservative t>3 discovery
# bar (Harvey-Liu-Zhu) so a no-loading name reliably classifies rate-agnostic.
ok("no rate loading -> rate-agnostic (t>3 bar)", rr.classify(rr.duration_betas(rets3, rmkt, dL, dS, dC), tmin=3.0) == "rate-agnostic")

# 4) curve_state + change series from a tiny planted history
hist = {"dates": ["2026-06-24", "2026-06-25", "2026-06-26"],
        "y5": [1.80, 1.82, 1.85], "y10": [2.00, 2.03, 2.04], "y30": [2.30, 2.33, 2.31]}
cs = rr.curve_state(hist)
ok("curve_state returns L/S/C + deltas", all(k in cs for k in ("L", "S", "C", "dL", "dS", "dC")), cs)
chg = rr.curve_change_series(hist)
ok("change series length = N-1", len(chg["dL"]) == 2, chg)

print("\n" + ("ALL RATE-REAL TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
