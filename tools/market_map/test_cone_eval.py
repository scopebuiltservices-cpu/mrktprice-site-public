"""Planted-structure tests for cone_eval.py — inverse-normal / Wilson / interval-score primitives,
and the STRUCTURAL behaviour of the walk-forward coverage backtest under known VR regimes:
  mean-reverting (VR<1)  -> VR-aware bands are NARROWER than naive sqrt-time
  trending      (VR>1)   -> VR-corrected champion bands are WIDER than naive sqrt-time
  random walk   (VR~1)   -> every source is ~calibrated at the nominal level
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cone_eval as CE

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


def close(a, b, t=1e-4):
    return a is not None and abs(a - b) <= t


# --- primitives ---
ok("norm_ppf(0.5)=0", close(CE._norm_ppf(0.5), 0.0))
ok("norm_ppf(0.975)~1.95996", close(CE._norm_ppf(0.975), 1.959964, 1e-4))
ok("norm_ppf(0.95)~1.64485", close(CE._norm_ppf(0.95), 1.644854, 1e-4))
lo, hi = CE.wilson(90, 100)
ok("wilson 90/100 brackets 0.9", lo < 0.9 < hi and lo > 0.8 and hi < 0.96, (lo, hi))
ok("interval score inside = width", close(CE.interval_score(0.0, -1.0, 1.0, 0.1), 2.0))
ok("interval score below adds penalty", CE.interval_score(-2.0, -1.0, 1.0, 0.1) > 2.0)

# --- random walk (VR ~ 1): every source roughly calibrated at 90% ---
rng = random.Random(11)
rw = [100.0]
for _ in range(500):
    rw.append(rw[-1] * math.exp(rng.gauss(0, 0.01)))
res = CE.backtest(rw, H=21, level=0.90, min_train=60)
for s in ("sqrt_time", "champion", "arbiter"):
    c = res["sources"][s]["coverage"]
    ok("RW %s coverage near 0.90" % s, 0.80 <= c <= 0.99, c)
ok("RW recommends a valid source", res["recommend"] in res["sources"])

# --- mean-reverting (VR<1): AR(1) on log-price, kappa>0 -> narrower VR-aware bands ---
rng = random.Random(3)
x = math.log(100.0); mu = x; mr = [100.0]
for _ in range(500):
    x = x + 0.06 * (mu - x) + rng.gauss(0, 0.012)
    mr.append(math.exp(x))
rmr = CE.backtest(mr, H=21, level=0.90, min_train=60)
ok("MR arbiter half-width < sqrt-time (VR<1 narrows)",
   rmr["sources"]["arbiter"]["meanHalfWidth"] < rmr["sources"]["sqrt_time"]["meanHalfWidth"],
   (rmr["sources"]["arbiter"]["meanHalfWidth"], rmr["sources"]["sqrt_time"]["meanHalfWidth"]))
ok("MR champion half-width < sqrt-time",
   rmr["sources"]["champion"]["meanHalfWidth"] < rmr["sources"]["sqrt_time"]["meanHalfWidth"])

# --- trending / momentum (VR>1): positive return autocorr -> wider VR-corrected bands ---
rng = random.Random(5)
prev = 0.0; tr = [100.0]
for _ in range(500):
    e = rng.gauss(0, 0.01)
    r = 0.45 * prev + e; prev = r
    tr.append(tr[-1] * math.exp(r))
rtr = CE.backtest(tr, H=21, level=0.90, min_train=60)
ok("TR champion half-width > sqrt-time (VR>1 widens)",
   rtr["sources"]["champion"]["meanHalfWidth"] > rtr["sources"]["sqrt_time"]["meanHalfWidth"],
   (rtr["sources"]["champion"]["meanHalfWidth"], rtr["sources"]["sqrt_time"]["meanHalfWidth"]))

# --- structural output invariants ---
ok("every source reports coverage+intervalScore+wilson",
   all(("coverage" in v and "intervalScore" in v and "wilson" in v) for v in res["sources"].values() if v.get("n")))
ok("advisory note present", "serially correlated" in res["note"])
ok("thin history -> empty-ish", CE.backtest([100, 101, 102], H=21)["recommend"] is None)

print("\nALL cone_eval PASS" if not fail else "\nSOME cone_eval TESTS FAILED")
sys.exit(1 if fail else 0)
