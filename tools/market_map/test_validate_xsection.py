#!/usr/bin/env python3
"""Tests for validate_xsection.py. Run: python3 test_validate_xsection.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_xsection as vx

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

good = {"asof": "2026-06-27", "tickers": ["AAPL", "MSFT"],
        "corr": [[1.0, 0.4], [0.4, 1.0]], "beta": {"AAPL": 1.2, "MSFT": 1.0}, "rs": {"AAPL": 80, "MSFT": 55}}
ok("valid payload -> no errors", vx.validate(good) == [], vx.validate(good))
ok("missing tickers flagged", any("tickers" in e for e in vx.validate({"asof": "x"})))
ok("corr wrong size flagged", any("corr must" in e for e in vx.validate({"asof": "x", "tickers": ["A", "B"], "corr": [[1.0]]})))
ok("corr out-of-range flagged", any("out of [-1,1]" in e for e in vx.validate({"asof": "x", "tickers": ["A", "B"], "corr": [[1.0, 9.0], [9.0, 1.0]]})))
ok("beta out-of-band flagged", any("beta[" in e for e in vx.validate({"asof": "x", "tickers": ["A"], "beta": {"A": 99.0}})))
ok("null corr entries allowed", vx.validate({"asof": "x", "tickers": ["A", "B"], "corr": [[1.0, None], [None, 1.0]]}) == [])

print("\n" + ("ALL VALIDATE-XSECTION TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
