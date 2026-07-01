"""Network-free test for expect_board.expect_for: forward band + last reconciliation + accuracy;
thin-history gating; ETF skip."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expect_board as B

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


rng = random.Random(4)
c = [100.0]; v = []
for _ in range(300):
    c.append(c[-1] * math.exp(rng.gauss(0, 0.011))); v.append(1e6 * math.exp(rng.gauss(0, 0.25)))
v.append(1e6)

blk = B.expect_for(c, v, H=21, level=0.90)
ok("block produced", blk is not None)
ok("forward band is a labeled prediction interval", blk["band"]["kind"] == "prediction interval" and blk["band"]["level"] == 0.90)
ok("band half-width % present", blk["band"]["halfWidthPct"] > 0)
ok("last reconciliation present", blk["last"] is not None)
ok("last has range/vol/volume/containment", all(k in blk["last"] for k in ("range", "vol", "volume", "containment")))
ok("accuracy has containment + mean ratios", blk["accuracy"] and blk["accuracy"]["containment"] is not None and blk["accuracy"]["meanRangeRatio"] is not None)
ok("H/level echoed", blk["H"] == 21 and blk["level"] == 0.90)

# idempotence
b2 = B.expect_for(c, v, H=21, level=0.90)
ok("idempotent band", b2["band"]["hi"] == blk["band"]["hi"])

# gating
ok("thin history -> None", B.expect_for(c[:40], v[:40]) is None)
ok("no volume still works (range/vol only)", B.expect_for(c, [], H=21) is not None)
ok("ETF skipped", B._is_equity({"t": "SPY", "etf": True}) is False)
ok("plain equity kept", B._is_equity({"t": "AAPL"}) is True)

print("\nALL expect_board PASS" if not fail else "\nSOME expect_board TESTS FAILED")
sys.exit(1 if fail else 0)
