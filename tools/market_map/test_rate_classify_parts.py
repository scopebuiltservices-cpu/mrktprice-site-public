#!/usr/bin/env python3
"""Tests for rate_real.classify_parts — direction vs statistical-confidence split (audit F5/R008).
Run: python3 test_rate_classify_parts.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_real as rr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# significant level beta, negative sign -> long-duration / rate-down beneficiary, CONFIDENT
p = rr.classify_parts({"bL": -0.8, "tL": 3.1, "bS": 0.1, "tS": 0.4, "bC": 0.0, "tC": 0.1})
ok("dominant driver = level", p["driver"] == "level", p)
ok("negative level beta -> rate-down direction", p["betaSign"] == "rate-down", p)
ok("t=3.1 >= 2 -> confident", p["confident"] is True, p)
ok("tAbs surfaced", p["tAbs"] == 3.1, p)

# SUB-threshold level beta -> direction still reported, but NOT confident (the whole point of the split)
p2 = rr.classify_parts({"bL": 0.5, "tL": 1.2, "bS": 0.0, "tS": 0.3, "bC": 0.0, "tC": 0.1})
ok("sub-threshold keeps direction (rate-up)", p2["betaSign"] == "rate-up", p2)
ok("sub-threshold -> NOT confident", p2["confident"] is False, p2)
# classify() would have collapsed this to 'rate-agnostic', losing the sign:
ok("classify() drops the sign below tmin", rr.classify({"bL": 0.5, "tL": 1.2}) == "rate-agnostic")

# slope-dominant, positive -> steepener
p3 = rr.classify_parts({"bL": 0.1, "tL": 0.5, "bS": 0.6, "tS": 2.6, "bC": 0.0, "tC": 0.1})
ok("slope driver, positive -> steepener + confident", p3["driver"] == "slope" and p3["betaSign"] == "steepener" and p3["confident"], p3)

# empty / missing -> neutral, not confident
ok("empty -> neutral", rr.classify_parts({}) == {"betaSign": "neutral", "confident": False, "driver": None, "tAbs": None})
ok("None -> neutral", rr.classify_parts(None)["betaSign"] == "neutral")

# the class string is unchanged (back-compat)
ok("classify() still returns the legacy label", rr.classify({"bL": -0.8, "tL": 3.1}) == "long-duration (rate-down beneficiary)")

print("\n" + ("ALL RATE-CLASSIFY-PARTS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
