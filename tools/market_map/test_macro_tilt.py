#!/usr/bin/env python3
"""Tests for macro_tilt.py — full commodity + real-rate integration. Run: python3 test_macro_tilt.py"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_tilt as M

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)
def close(a, b, t=1e-12): return abs(a - b) <= t * (1 + abs(b))

# every commodity beta enters (not just OIL): a copper-only move must move the tilt
ok("commodity beyond OIL counts", close(M.macro_tilt({"COPPER": 0.5}, {"COPPER": 0.04}), 0.02))
ok("sums multiple commodities", close(M.macro_tilt({"OIL": 0.3, "GOLD": 0.2}, {"OIL": 0.1, "GOLD": -0.05}), 0.3*0.1 + 0.2*-0.05))
# MKT excluded (board scores market beta separately as drag)
ok("MKT excluded by default", close(M.macro_tilt({"MKT": 1.0, "OIL": 0.2}, {"MKT": 0.05, "OIL": 0.1}), 0.2*0.1))
# real-rate curve contribution
ok("rate_real bL*dL+bS*dS+bC*dC", close(M.rate_real_tilt({"bL": -3.0, "bS": 1.0, "bC": 0.5}, {"dL": 0.01, "dS": -0.02, "dC": 0.004}), -3.0*0.01 + 1.0*-0.02 + 0.5*0.004))
ok("rate_real None-safe", M.rate_real_tilt(None, None) == 0.0 and M.rate_real_tilt({"bL": 1}, None) == 0.0)
# combined: with real curve present, nominal RATE is NOT double counted
c = M.combined_tilt({"OIL": 0.2, "RATE": 0.5}, {"OIL": 0.1, "RATE": 0.03}, {"bL": -2.0, "bS": 0, "bC": 0}, {"dL": 0.01, "dS": 0, "dC": 0})
ok("combined excludes nominal RATE when real curve present", close(c, 0.2*0.1 + (-2.0*0.01)))
# combined: no real curve -> nominal RATE included as fallback
c2 = M.combined_tilt({"OIL": 0.2, "RATE": 0.5}, {"OIL": 0.1, "RATE": 0.03}, None, None)
ok("combined uses nominal RATE fallback when no real curve", close(c2, 0.2*0.1 + 0.5*0.03))
# NaN-safe
ok("NaN beta skipped", close(M.macro_tilt({"OIL": float("nan"), "GOLD": 0.2}, {"OIL": 0.1, "GOLD": 0.1}), 0.02))

# golden lock
GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "macro_golden.json")
if not os.path.exists(GOLD):
    json.dump(M.gen_fixture(), open(GOLD, "w"), separators=(",", ":"))
g = json.load(open(GOLD))
allok = True
for r in g["rows"]:
    if not (close(M.macro_tilt(r["betas"], r["moves"]), r["macroTilt"]) and
            close(M.rate_real_tilt(r["rate"], r["ratemove"]) if r["rate"] else 0.0, r["rateRealTilt"]) and
            close(M.combined_tilt(r["betas"], r["moves"], r["rate"], r["ratemove"]), r["combined"])):
        allok = False
ok("golden fixture reproduced", allok)

print("\n" + ("ALL MACRO-TILT TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
