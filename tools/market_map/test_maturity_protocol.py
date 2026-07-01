#!/usr/bin/env python3
"""Leakage-proof tests for maturity_protocol.py. Run: python3 test_maturity_protocol.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maturity_protocol import MaturityProtocol

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- three-timestamp bookkeeping ---
mp = MaturityProtocol(embargo=None)          # per-record E = H
f = mp.issue("a", issue_t=10, H=5, mu=0.0, sigma=1.0, lower=-1.6, upper=1.6)
ok("maturity_t = issue_t + H", f["maturityT"] == 15)
ok("inclusion_t = maturity_t + H (embargo=H)", f["inclusionT"] == 20)

# not matured before maturity time; no residual usable
ok("nothing matures before maturity_t", mp.observe(14, {"a": 0.5}) == [], mp.open_count())
mat = mp.observe(15, {"a": 0.5})
ok("matures at maturity_t when outcome known", len(mat) == 1 and mat[0]["covered"] is True, mat)

# --- EMBARGO: residual is NOT usable until inclusion_t, even though matured ---
ok("not in pool at issue_t < inclusion_t (embargo blocks)", mp.calibration_pool(19) == [], "19<20")
ok("enters pool at issue_t >= inclusion_t", len(mp.calibration_pool(20)) == 1)

# --- NO LOOKAHEAD across a full stream: every residual used by a forecast issued at T
#     had its OUTCOME known strictly before T ---
random.seed(4)
mp2 = MaturityProtocol(embargo=None)
H = 5
closes = [100.0]
for _ in range(400):
    closes.append(closes[-1] * (1 + random.gauss(0, 0.01)))
# issue one forecast per step; observe as outcomes arrive; every step, snapshot the pool used
leak = False
for t in range(0, len(closes) - H):
    # a forecast can only use residuals matured+embargoed before t
    pool = mp2.calibration_pool(t, horizon=H)
    for r in pool:
        if r["maturityT"] > t:            # its outcome would not be known yet -> leakage
            leak = True
        if r["inclusionT"] > t:           # embargo violated
            leak = True
    mp2.issue(t, issue_t=t, H=H, mu=0.0, sigma=0.01, lower=-0.03, upper=0.03)
    # outcomes for anything maturing at t
    realized = {fid: (closes[fid + H] / closes[fid] - 1.0) for fid in range(0, t + 1) if fid + H <= t}
    mp2.observe(t, realized)
ok("stream: no lookahead + embargo respected across 395 steps", not leak)
ok("stream: leakage invariant self-check holds", mp2.leakage_ok())
ok("stream: some residuals actually matured", len(mp2.matured_records(horizon=H)) > 100,
   len(mp2.matured_records(horizon=H)))

# --- matured records are in coverage_strata shape (covered/horizon/sign) ---
rec = mp2.matured_records(horizon=H)[0]
ok("matured record carries covered/H/sign/residual/stud", all(k in rec for k in ("covered", "H", "sign", "residual", "stud")), list(rec))

# --- explicit embargo value overrides per-record H ---
mp3 = MaturityProtocol(embargo=10)
g = mp3.issue("z", issue_t=0, H=5, mu=0, sigma=1, lower=-2, upper=2)
ok("explicit embargo=10 -> inclusion_t = maturity_t + 10", g["inclusionT"] == 15)

print("\n" + ("ALL MATURITY-PROTOCOL TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
