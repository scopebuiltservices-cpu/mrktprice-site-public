#!/usr/bin/env python3
"""Locks the Python engine_ref to the committed golden fixture (tools/engine_golden.json).
Together with tools/test_engine_parity.mjs (which locks engine.js to the SAME fixture) this gives
exact Py<->JS value parity for EMA / rolling-vol / OU / variance-ratio. Run: python3 test_engine_ref.py"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_ref as er

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine_golden.json")
g = json.load(open(GOLD))
I, X = g["inputs"], g["expected"]

def close(a, b, tol=1e-12):
    return abs(a - b) <= tol * (1 + abs(b))

# EMA
em = er.ema(I["ema_c"], I["ema_N"])
ok("ema matches fixture", len(em) == len(X["ema"]) and all(close(em[i], X["ema"][i]) for i in range(len(em))))
# HV
hv = er.hv_roll_series(I["hv_r"], I["hv_w"])
ok("hvRollSeries matches fixture", len(hv) == len(X["hv"]) and all(close(hv[i], X["hv"][i]) for i in range(len(hv))))
# OU
ou = er.ou_fit(I["ou_x"])
ok("ou_fit matches fixture", all(close(ou[k], X["ou"][k]) for k in ("phi", "sePhi", "theta", "mu", "muPrice", "halfLife", "sigmaX2", "z", "last")), {k: (ou[k], X["ou"][k]) for k in ("phi",)})
ok("ou_fit meanRev bool matches", ou["meanRev"] == X["ou"]["meanRev"])
# VR
vr = er.variance_ratio(I["vr_r"], I["vr_q"])
ok("variance_ratio matches fixture", close(vr["vr"], X["vr"]["vr"]) and close(vr["z"], X["vr"]["z"]))

# guard rails: OU on too-short series returns None; VR degenerate guard
ok("ou_fit None when <30", er.ou_fit([1.0] * 10) is None)
ok("variance_ratio degenerate guard", er.variance_ratio([0.0] * 20, 4) == {"vr": 1, "z": 0})

print("\n" + ("ALL ENGINE-REF TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
