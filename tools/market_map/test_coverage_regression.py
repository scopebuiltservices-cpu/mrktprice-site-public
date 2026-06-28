#!/usr/bin/env python3
"""Tests for coverage_regression.py. Run: python3 test_coverage_regression.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverage_regression as cr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

def rec(asof, clean, stable=100, sani=0, fmpDeg=False):
    return {"asof": asof, "dataQuality": {"clean": clean, "degraded": 2, "reject": 1},
            "driftCensus": {"stable": stable, "moderate": 0, "significant": 0, "baseline": 0},
            "sanitizedFields": sani, "fmpDegraded": fmpDeg}

# flatten pulls numerics
fl = cr.flatten(rec("2026-06-27", 480))
ok("flatten has dataQuality.clean", fl.get("dataQuality.clean") == 480, fl)
ok("flatten has driftCensus.stable", fl.get("driftCensus.stable") == 100)

# HARD: clean 480 -> 0
al = cr.compare(rec("a", 480), rec("b", 0))
ok("HARD on drop-to-zero", any(a[0] == "HARD" and a[1] == "dataQuality.clean" for a in al), al)

# WARN: clean 480 -> 100 (>50% drop, not zero)
al2 = cr.compare(rec("a", 480), rec("b", 100))
ok("WARN on >50% drop", any(a[0] == "WARN" for a in al2) and not any(a[0] == "HARD" for a in al2), al2)

# no alert on small change
al3 = cr.compare(rec("a", 480), rec("b", 470))
ok("no alert on small change", al3 == [], al3)

# fmpDegraded flip
al4 = cr.compare(rec("a", 480, fmpDeg=False), rec("b", 480, fmpDeg=True))
ok("HARD on fmpDegraded flip", any(a[0] == "HARD" and a[1] == "fmpDegraded" for a in al4), al4)

# sanitizedFields zero is NOT a coverage regression
al5 = cr.compare(rec("a", 480, sani=5), rec("b", 480, sani=0))
ok("sanitizedFields drop ignored", al5 == [], al5)

# check_log end-to-end + exit codes
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "health_log.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps(rec("2026-06-25", 480)) + "\n")
    rc, al, note = cr.check_log(p)
    ok("single record -> rc 0 (nothing to compare)", rc == 0 and al == [])
    with open(p, "a") as f:
        f.write(json.dumps(rec("2026-06-26", 0)) + "\n")
    rc2, al2, _ = cr.check_log(p)
    ok("two records, feed died -> rc 1", rc2 == 1)
    ok("main(--soft) downgrades to rc 0", cr.main([p, "--soft"]) == 0)
    ok("main hard -> rc 1", cr.main([p]) == 1)

print("\n" + ("ALL COVERAGE-REGRESSION TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
