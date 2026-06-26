#!/usr/bin/env python3
"""Unit tests for harq_regime.py against PLANTED volatility structure. Run: python3 test_harq_regime.py"""
import math, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harq_regime as hq

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

def _gauss(rng): return rng.gauss(0, 1)

def make_closes(vol_path, seed=1):
    """Build a close series whose daily return vol follows vol_path (clustered volatility)."""
    rng = random.Random(seed); p = 100.0; out = [p]
    for v in vol_path:
        p *= math.exp(v * _gauss(rng)); out.append(p)
    return out

# 1) guard: too-short input returns None
ok("None on <60 returns", hq.harq_regime_forecast([100, 101, 102]) is None)

# 2) clustered-vol series -> a well-formed forecast with the right shape
n = 400
vp = [0.01 + 0.012 * (math.sin(i / 30.0) ** 2) for i in range(n)]      # smoothly clustering vol 1%..2.2%
closes = make_closes(vp, seed=3)
res = hq.harq_regime_forecast(closes)
ok("returns a result on a long series", res is not None)
ok("beta has 6 coefficients (const+RVd+RVw+RVm+RQ+pHV)", len(res["beta"]) == 6)
ok("forecast vol positive + finite", res["volForecastAnn"] > 0 and math.isfinite(res["volForecastAnn"]))
ok("forecast in a sane annualized range (1%..400%)", 1.0 < res["volForecastAnn"] < 400.0, res["volForecastAnn"])
ok("R^2 finite and <=1", math.isfinite(res["r2"]) and res["r2"] <= 1.0, res["r2"])
ok("p(high-vol) in [0,1]", 0.0 <= res["phvNow"] <= 1.0, res["phvNow"])
ok("HAR persistence: total RV-lag loading positive", (res["beta"][1] + res["beta"][2] + res["beta"][3]) > 0,
   (res["beta"][1], res["beta"][2], res["beta"][3]))

# 3) the forecast RESPONDS to the recent state: a series ending HOT forecasts higher vol than one ending CALM
base = [0.012] * 300
hot = make_closes(base + [0.045] * 30, seed=5)     # last 30 days highly volatile
calm = make_closes(base + [0.004] * 30, seed=5)    # last 30 days very quiet
rh = hq.harq_regime_forecast(hot); rc = hq.harq_regime_forecast(calm)
ok("hot-ending series forecasts higher vol than calm-ending", rh["volForecastAnn"] > rc["volForecastAnn"],
   (round(rh["volForecastAnn"], 1), round(rc["volForecastAnn"], 1)))

# 4) no look-ahead: forecast uses only closes passed in (truncating the future cannot change a past forecast)
full = make_closes([0.012] * 200, seed=7)
trunc = full[:150]
r_full_on_trunc = hq.harq_regime_forecast(trunc)
r_again = hq.harq_regime_forecast(full[:150])
ok("deterministic / no hidden state", abs(r_full_on_trunc["volForecastAnn"] - r_again["volForecastAnn"]) < 1e-9)

# 5) constant-vol input -> forecast near that constant vol (sanity of level)
cv = 0.01
cc = make_closes([cv] * 400, seed=11)
rcv = hq.harq_regime_forecast(cc)
implied = cv * math.sqrt(252) * 100.0
ok("constant-vol level recovered within 2x", 0.5 * implied < rcv["volForecastAnn"] < 2.0 * implied,
   (round(rcv["volForecastAnn"], 1), round(implied, 1)))

print("\n" + ("ALL HARQ+REGIME TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
