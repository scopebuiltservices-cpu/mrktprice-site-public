#!/usr/bin/env python3
"""Unit tests for intraday_engine.py against PLANTED structure. Run: python3 test_intraday.py"""
import math, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intraday_engine as ie
rng = random.Random(1)
FAILS = []
def ok(name, cond, d=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  -> " + str(d)))
    if not cond: FAILS.append(name)

# 1) robust median/MAD
ok("median odd", ie._median([3, 1, 2]) == 2)
ok("median even", abs(ie._median([1, 2, 3, 4]) - 2.5) < 1e-9)
ok("MAD of constant is 0", ie._mad([5, 5, 5]) == 0.0)
ok("MAD positive for dispersed data", ie._mad([-2, -1, 0, 1, 2]) > 0.8)

# 2) time-of-day normalizers + abnormality (history has within-bucket dispersion)
hist = [{"bucket": b % 5,
         "vol": 1e6 * math.exp((b % 5) * 0.1 + rng.gauss(0, 0.25)),
         "rv": 1e-5 * math.exp(rng.gauss(0, 0.4))} for b in range(2000)]
norms = ie.tod_normalizers(hist)
ok("normalizers cover all buckets", set(norms.keys()) == {0, 1, 2, 3, 4})
ok("normalizer scale is positive", norms[2]["sV"] > 0 and norms[2]["sRV"] > 0)
spike = {"bucket": 2, "vol": 1e6 * math.exp(0.2) * 6.0, "rv": 1e-5 * 6.0}
zV, zRV = ie.abnormality(spike, norms)
ok("volume spike -> high zV", zV > 3, zV)
ok("RV spike -> high zRV", zRV > 3, zRV)
ok("gate_A trips on dual spike", ie.gate_A(zV, zRV, 1.5, 1.5) == 1)
ok("gate_A does NOT trip on calm bar", ie.gate_A(0.1, 0.1, 1.5, 1.5) == 0)

# 3) consecutive-confirmation trigger fires at K and resets on a break
ok("trigger at K=3 (..11111)", ie.consecutive_trigger([0, 0, 1, 1, 1, 1], 3)[0] == 4)
ok("no trigger if never K consecutive", ie.consecutive_trigger([1, 0, 1, 0, 1, 0], 3)[0] is None)
ok("counter resets on break", ie.consecutive_trigger([1, 1, 0, 1, 1, 1], 3)[0] == 5)

# 4) log-space integration: constant drift mu over h -> p_T + h*mu ; price = exp
lp = ie.project_logpath(2.0, [0.01, 0.01, 0.01])
ok("cumulative log drift", abs(lp[-1] - (2.0 + 0.03)) < 1e-12)
ok("price = exp(logpath)", abs(math.exp(lp[0]) - math.exp(2.01)) < 1e-9)

# 5) parametric band widens with horizon (sqrt-time) and brackets the center
lo, hi = ie.parametric_band([2.0, 2.0, 2.0], [0.02, 0.02, 0.02], [0.0, 0.0, 0.0], z=1.0)
w = [hi[i] - lo[i] for i in range(3)]
ok("band widens with horizon", w[0] < w[1] < w[2])
ok("band width ~ 2*z*sqrt(h)*sigma", abs(w[2] - 2 * (3 ** 0.5) * 0.02) < 1e-9, w[2])

# 6) conformal band uses trigger-matched residual quantiles (all-negative -> band shifts down)
resid = {0: [(-0.05 + 0.0003 * i) for i in range(100)]}    # range -0.05 .. -0.0203 (all negative)
clo, chi = ie.conformal_band([2.0], resid, alpha=0.90)
ok("conformal band present when >=8 residuals", clo[0] == clo[0] and chi[0] == chi[0])
ok("conformal reflects negative residuals (hi<center)", chi[0] < 2.0, chi[0])
ok("conformal lo below hi", clo[0] < chi[0])

# 7) decision rule acts on the bound, not the point
d = ie.decision(2.0, [2.05], [1.99], 0, cost=0.0)
ok("positive upper-bound edge -> tradable long", d["tradable"] and d["side"] == "long", d)
d2 = ie.decision(2.0, [2.001], [1.999], 0, cost=0.01)
ok("edge below cost -> not tradable (conditional)", not d2["tradable"], d2)

# 8) NO-LOOK-AHEAD on planted persistent spike (volume+RV+drift from window 8)
hist2 = [{"bucket": k, "vol": 1e6 * math.exp(rng.gauss(0, 0.2)), "rv": 9e-6 * math.exp(rng.gauss(0, 0.4))}
         for _ in range(30) for k in range(26)]
def synth(n):
    bars = []; p = 4.6
    for k in range(n):
        hot = k >= 8
        r = rng.gauss(0.004 if hot else 0.0, 0.003)
        vol = 1e6 * math.exp(rng.gauss(0, 0.2)) * (6.0 if hot else 1.0)
        rv = 9e-6 * (6.0 if hot else 1.0) * math.exp(rng.gauss(0, 0.15))   # regime-level RV (sub-bar aggregated)
        p += r; bars.append({"bucket": k, "ret": r, "rv": rv, "vol": vol, "p": p})
    return bars
full = synth(26)
out = ie.evaluate(full, hist2, {"K": 3, "warm": 4})
ok("planted persistent spike triggers", out["triggered"], out.get("T"))
if out["triggered"]:
    T = out["T"]
    trunc = ie.evaluate(full[:T + 1], hist2, {"K": 3, "warm": 4})
    ok("trigger index identical when future hidden (no look-ahead)", trunc["T"] == T, (trunc.get("T"), T))
    ok("projection has H horizons", len(out["center"]) == out["params"]["H"])
    ok("center path finite + positive", all(x > 0 and math.isfinite(x) for x in out["center"]))
    ok("band brackets center at h0", out["hi"][0] >= out["center"][0] >= out["lo"][0])
    ok("trigger is at/after the planted spike (k>=8)", T >= 8, T)

# 9) coverage audit
ok("coverage = hit fraction", abs(ie.coverage([1, 1, 0, 1]) - 0.75) < 1e-9)
_ev = [{"lo": 0.95, "hi": 1.05, "center": 1.0, "realized": (1.15 if i == 0 else 1.0 + 0.01 * (i - 5)),
        "pT": 0.98, "gatePass": i % 2 == 0, "rwLo": 0.80, "rwHi": 1.20} for i in range(10)]
_a = ie.audit_coverage(_ev, 0.90)
ok("audit coverage = 9/10", abs(_a["coverage"] - 0.9) < 1e-9, _a["coverage"])
ok("audit RW baseline wider -> covers all", _a["rwBaselineCoverage"] == 1.0, _a["rwBaselineCoverage"])
ok("audit avg band width 0.10", abs(_a["avgBandWidth"] - 0.10) < 1e-9, _a["avgBandWidth"])
ok("audit empty -> None", ie.audit_coverage([]) is None)

print("\n" + ("ALL INTRADAY ENGINE TESTS PASSED" if not FAILS else "%d FAILED: %s" % (len(FAILS), FAILS)))
raise SystemExit(1 if FAILS else 0)
