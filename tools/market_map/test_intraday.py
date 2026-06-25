#!/usr/bin/env python3
"""Unit tests for intraday_engine.py against PLANTED structure. Run: python3 test_intraday.py"""
import math, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intraday_engine as ie
FAILS = []
def ok(name, cond, d=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  -> " + str(d)))
    if not cond: FAILS.append(name)

# 1) robust median/MAD
ok("median odd", ie._median([3, 1, 2]) == 2)
ok("median even", abs(ie._median([1, 2, 3, 4]) - 2.5) < 1e-9)
ok("MAD of constant is 0", ie._mad([5, 5, 5]) == 0.0)
ok("MAD scales ~sigma for normal-ish", 0.8 < ie._mad([(-2,-1,0,1,2)[i] for i in range(5)]) < 3.5)

# 2) time-of-day normalizers + abnormality: a bar far above its bucket's history flags high z
hist = [{"bucket": b % 5, "vol": 1e6 * math.exp((b % 5) * 0.1), "rv": 1e-5} for b in range(500)]
norms = ie.tod_normalizers(hist)
ok("normalizers cover all buckets", set(norms.keys()) == {0, 1, 2, 3, 4})
spike = {"bucket": 2, "vol": 1e6 * math.exp(0.2) * 6.0, "rv": 1e-5 * 5.0}
zV, zRV = ie.abnormality(spike, norms)
ok("volume spike -> high zV", zV > 3, zV)
ok("RV spike -> high zRV", zRV > 3, zRV)
ok("gate_A trips on dual spike", ie.gate_A(zV, zRV, 1.5, 1.5) == 1)
ok("gate_A does NOT trip on calm bar", ie.gate_A(0.1, 0.1, 1.5, 1.5) == 0)

# 3) consecutive-confirmation trigger fires at K and resets on a break
ok("trigger at K=3 (....11111)", ie.consecutive_trigger([0,0,1,1,1,1], 3)[0] == 4)
ok("no trigger if never K consecutive", ie.consecutive_trigger([1,0,1,0,1,0], 3)[0] is None)
ok("counter resets on break", ie.consecutive_trigger([1,1,0,1,1,1], 3)[0] == 5)

# 4) log-space integration: constant drift mu over h -> p_T + h*mu ; price = exp
lp = ie.project_logpath(2.0, [0.01, 0.01, 0.01])
ok("cumulative log drift", abs(lp[-1] - (2.0 + 0.03)) < 1e-12)
ok("price = exp(logpath)", abs(math.exp(lp[0]) - math.exp(2.01)) < 1e-9)

# 5) parametric band widens with horizon (sqrt-time) and brackets the center
lo, hi = ie.parametric_band([2.0, 2.0, 2.0], [0.02, 0.02, 0.02], [0.0, 0.0, 0.0], z=1.0)
w = [hi[i] - lo[i] for i in range(3)]
ok("band widens with horizon", w[0] < w[1] < w[2])
ok("band width ~ 2*z*sqrt(h)*sigma", abs(w[2] - 2 * (3 ** 0.5) * 0.02) < 1e-9, w[2])

# 6) conformal band uses trigger-matched residual quantiles (skewed -> asymmetric band)
resid = {0: [(-0.05 + 0.001 * i) for i in range(100)]}   # all-negative errors -> band shifts down
clo, chi = ie.conformal_band([2.0], resid, alpha=0.90)
ok("conformal band present when >=8 residuals", clo[0] == clo[0] and chi[0] == chi[0])
ok("conformal reflects negative-skew residuals (hi<=center)", chi[0] <= 2.0 + 1e-6, chi[0])

# 7) decision rule acts on the bound, not the point
d = ie.decision(2.0, [2.05], [1.99], 0, cost=0.0)
ok("positive upper-bound edge -> tradable long", d["tradable"] and d["side"] == "long", d)
d2 = ie.decision(2.0, [2.001], [1.999], 0, cost=0.01)
ok("edge below cost -> not tradable (conditional)", not d2["tradable"], d2)

# 8) NO-LOOK-AHEAD: truncating the future must not change the trigger decision up to that point
rng = random.Random(11)
def synth(n, mu_from=None):
    bars = []; p = 4.6
    for k in range(n):
        # plant a persistent up-drift + volume/vol spike from window 8 onward
        hot = k >= 8
        mu = 0.004 if hot else 0.0
        r = rng.gauss(mu, 0.003)
        vol = 1e6 * math.exp(rng.gauss(0, 0.2)) * (5.0 if hot else 1.0)
        rv = (r * r + 1e-8) * (5.0 if hot else 1.0)
        p += r; bars.append({"bucket": k, "ret": r, "rv": rv, "vol": vol, "p": p})
    return bars
hist2 = [{"bucket": k % 26, "vol": 1e6 * math.exp(rng.gauss(0, 0.2)), "rv": 9e-6 + 1e-8} for _ in range(20) for k in range(26)]
full = synth(26)
out_full = ie.evaluate(full, hist2, {"K": 3, "warm": 4})
ok("planted persistent spike triggers", out_full["triggered"], out_full.get("T"))
if out_full["triggered"]:
    T = out_full["T"]
    # evaluating only up to T must yield the SAME trigger index (no future info used)
    out_trunc = ie.evaluate(full[:T + 1], hist2, {"K": 3, "warm": 4})
    ok("trigger index identical when future is hidden (no look-ahead)", out_trunc["T"] == T, (out_trunc.get("T"), T))
    ok("projection has H horizons", len(out_full["center"]) == out_full["params"]["H"])
    ok("center path is finite + positive", all(x > 0 and math.isfinite(x) for x in out_full["center"]))
    ok("band brackets center (hi>=center>=lo) at h0",
       out_full["hi"][0] >= out_full["center"][0] >= out_full["lo"][0])

# 9) coverage audit math
ok("coverage = hit fraction", abs(ie.coverage([1, 1, 0, 1]) - 0.75) < 1e-9)

print("\n" + ("ALL INTRADAY ENGINE TESTS PASSED" if not FAILS else "%d FAILED: %s" % (len(FAILS), FAILS)))
raise SystemExit(1 if FAILS else 0)
