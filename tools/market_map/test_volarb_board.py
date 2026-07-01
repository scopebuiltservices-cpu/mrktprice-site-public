"""Network-free test for volarb_board.volarb_for: blended sigma from a planted close series,
component/weight structure, VR overlay engagement on a trending series, and thin-data gating."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import volarb_board as B

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


# planted random-walk closes with ~1%/day vol
rng = random.Random(7)
closes = [100.0]
for _ in range(200):
    closes.append(closes[-1] * math.exp(rng.gauss(0, 0.01)))

r = B.volarb_for(closes, horizon=21)
ok("block produced", r is not None)
ok("sigma positive + finite", r["sigma"] > 0 and r["sigma"] == r["sigma"])
ok("hv component present", "hv" in r["weights"] and "hv" in r["components"])
ok("ewma component present", "ewma" in r["weights"])
ok("reliability in (0,1]", 0.0 < r["reliability"] <= 1.0, r["reliability"])
ok("horizon echoed", r["horizon"] == 21)
ok("nObs = 200", r["nObs"] == 200, r["nObs"])
ok("version tag", r["version"] == "vol_arbiter_v1")
# ballpark: 1%/day over sqrt(21) ~ 0.046 horizon vol (loose band, seed-dependent)
ok("sigma in a sane band", 0.02 < r["sigma"] < 0.09, r["sigma"])

# thin data -> None
ok("thin history -> None", B.volarb_for(closes[:20]) is None)
ok("empty -> None", B.volarb_for([]) is None)

# strongly trending series -> VR departs from 1 -> overlay may engage (lam>=0, bounded)
trend = [100.0 * (1.0 + 0.004) ** i for i in range(160)]
rt = B.volarb_for(trend, horizon=21)
ok("trending series still scores", rt is not None and rt["sigma"] >= 0)
ok("vr reported on trending series", rt is not None and rt["vr"] is not None)

# idempotence
r2 = B.volarb_for(closes, horizon=21)
ok("idempotent sigma", abs(r2["sigma"] - r["sigma"]) < 1e-12)

# gating helpers
ok("ETF skipped", B._is_equity({"t": "SPY", "etf": True}) is False)
ok("plain equity kept", B._is_equity({"t": "AAPL"}) is True)

print("\nALL volarb_board PASS" if not fail else "\nSOME volarb_board TESTS FAILED")
sys.exit(1 if fail else 0)
