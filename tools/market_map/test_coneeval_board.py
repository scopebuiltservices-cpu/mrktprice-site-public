"""Network-free test for coneeval_board.coneeval_for: emits a compact per-name cone-coverage block
with a valid recommendation and per-source metrics; gates on thin history; skips ETFs/factors."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coneeval_board as B

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


# mean-reverting closes (VR<1) so sources genuinely differ
rng = random.Random(3)
x = math.log(100.0); mu = x; mr = [100.0]
for _ in range(400):
    x = x + 0.06 * (mu - x) + rng.gauss(0, 0.012)
    mr.append(math.exp(x))

blk = B.coneeval_for(mr, H=21, level=0.90, stride=5)
ok("block produced", blk is not None)
ok("recommend is a scored source", blk["recommend"] in blk["sources"], blk["recommend"])
ok("H/level echoed", blk["H"] == 21 and blk["level"] == 0.90)
ok("n>0 decision points", blk["n"] > 0)
for s in ("sqrt_time", "champion", "arbiter"):
    ok("source %s has cov+iS+calErr+hw" % s,
       all(k in blk["sources"][s] for k in ("cov", "iS", "calErr", "hw")))
ok("champion narrower than sqrt_time here (VR<1)",
   blk["sources"]["champion"]["hw"] < blk["sources"]["sqrt_time"]["hw"])
ok("reason string present", isinstance(blk["reason"], str) and len(blk["reason"]) > 0)

# stride subsampling stays consistent in structure
b2 = B.coneeval_for(mr, H=21, level=0.90, stride=10)
ok("coarser stride still recommends a valid source", b2 and b2["recommend"] in b2["sources"])

# gating
ok("thin history -> None", B.coneeval_for(mr[:40]) is None)
ok("empty -> None", B.coneeval_for([]) is None)
ok("ETF skipped", B._is_equity({"t": "SPY", "etf": True}) is False)
ok("plain equity kept", B._is_equity({"t": "AAPL"}) is True)

print("\nALL coneeval_board PASS" if not fail else "\nSOME coneeval_board TESTS FAILED")
sys.exit(1 if fail else 0)
