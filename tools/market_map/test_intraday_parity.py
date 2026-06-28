#!/usr/bin/env python3
"""Python side of the intraday Py<->JS golden-fixture parity (PDF priority 3, intraday_engine.js).
Generates tools/intraday_golden.json from intraday_engine.py on a COMMITTED input, then asserts the
Python reference reproduces it. tools/test_intraday_parity.mjs locks intraday_engine.js to the SAME file.
Only the deterministic estimators are compared (block-bootstrap SE is excluded — Python and JS use
different PRNGs there, so it is not bit-reproducible and keeps its planted-structure test).
Run: python3 test_intraday_parity.py"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intraday_engine as IE

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "intraday_golden.json")
F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

rets = [0.0012, -0.0008, 0.0021, -0.0015, 0.0009, 0.0003, -0.0011, 0.0017,
        -0.0006, 0.0014, 0.0002, -0.0019, 0.0008, 0.0011, -0.0004]
lam = 0.85
mu = sum(rets) / len(rets)
se = IE.rolling_se(rets, mu)
expected = {
    "ewma_drift": IE.ewma_drift(rets, lam),
    "rolling_se": se,
    "realized_quarticity": IE.realized_quarticity(rets),
    "signal_q": IE.signal_q(mu, se),
}
fixture = {"fixture_version": 1, "case": "intraday-deterministic-core",
           "inputs": {"rets": rets, "lam": lam, "mu": mu}, "expected": expected}

if not os.path.exists(GOLD):
    json.dump(fixture, open(GOLD, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(GOLD))

g = json.load(open(GOLD))
gi, gx = g["inputs"], g["expected"]
# Python must reproduce the committed expected from the committed inputs (regression lock)
muc = gi["mu"]; sec = IE.rolling_se(gi["rets"], muc)
ok("ewma_drift matches fixture", abs(IE.ewma_drift(gi["rets"], gi["lam"]) - gx["ewma_drift"]) <= 1e-12 * (1 + abs(gx["ewma_drift"])))
ok("rolling_se matches fixture", abs(sec - gx["rolling_se"]) <= 1e-12 * (1 + abs(gx["rolling_se"])))
ok("realized_quarticity matches fixture", abs(IE.realized_quarticity(gi["rets"]) - gx["realized_quarticity"]) <= 1e-12 * (1 + abs(gx["realized_quarticity"])))
ok("signal_q matches fixture", abs(IE.signal_q(muc, sec) - gx["signal_q"]) <= 1e-12 * (1 + abs(gx["signal_q"])))

print("\n" + ("ALL INTRADAY-PARITY (PY) TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
