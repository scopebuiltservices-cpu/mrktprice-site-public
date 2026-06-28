#!/usr/bin/env python3
"""Tests for schema_validate.py against the Draft 2020-12 schema files. Skips gracefully if jsonschema
is not installed (so verify_all passes on a stdlib-only box); CI installs it for the strict run.
Run: python3 test_schema_validate.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schema_validate as sv

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

try:
    import jsonschema  # noqa
    HAVE = True
except Exception:
    HAVE = False

if not HAVE:
    print("  skip  jsonschema not installed — schema gate is enforced in CI")
    print("\nSCHEMA-VALIDATE TESTS SKIPPED (no jsonschema)")
    raise SystemExit(0)

def w(d, name, obj):
    p = os.path.join(d, name); json.dump(obj, open(p, "w")); return p

with tempfile.TemporaryDirectory() as d:
    # cik
    ok("cik valid", sv.validate(w(d, "cik.json", {"AAPL": "0000320193"}))[0] is True)
    ok("cik bad (short)", sv.validate(w(d, "cik.json", {"AAPL": "320193"}))[0] is False)
    ok("cik bad (lowercase ticker)", sv.validate(w(d, "cik.json", {"aapl": "0000320193"}))[0] is False)
    # alpha_calib
    fb = {"asof": "2026-06-27", "horizonDays": 21, "n": 0, "mode": "fallback", "coef": None, "ic": None}
    ok("alpha_calib fallback valid", sv.validate(w(d, "alpha_calib.json", fb))[0] is True)
    fit = {"asof": "2026-06-27", "horizonDays": 21, "n": 500, "mode": "fitted", "coef": 0.5, "ic": 0.08}
    ok("alpha_calib fitted valid", sv.validate(w(d, "alpha_calib.json", fit))[0] is True)
    ok("alpha_calib fitted null coef -> fail (if/then)", sv.validate(w(d, "alpha_calib.json", dict(fit, coef=None)))[0] is False)
    ok("alpha_calib ic>1 -> fail", sv.validate(w(d, "alpha_calib.json", dict(fit, ic=1.5)))[0] is False)
    ok("alpha_calib bad mode -> fail", sv.validate(w(d, "alpha_calib.json", dict(fb, mode="weird")))[0] is False)
    # events
    ev = {"asof": "2026-06-27", "schemaVersion": "1.0", "nextHighImpact": {"date": "2026-07-01", "event": "CPI"},
          "daysToNext": 4, "upcoming": [{"date": "2026-07-01", "event": "CPI"}], "recent": []}
    ok("events valid", sv.validate(w(d, "events.json", ev))[0] is True)
    ok("events null nextHighImpact ok", sv.validate(w(d, "events.json", dict(ev, nextHighImpact=None, daysToNext=None)))[0] is True)
    ok("events bad event date -> fail", sv.validate(w(d, "events.json", dict(ev, upcoming=[{"date": "soon"}])))[0] is False)
    # universe
    uni = {"asof": "2026-06-27", "schemaVersion": "1.0", "source": "Live", "count": 1, "equities": 1,
           "sectors": {"Tech": 1}, "indexMembership": {"SP500": 1}, "dataQuality": None, "driftCensus": None,
           "members": [{"t": "AAPL", "sec": "Tech", "idx": ["SP500"], "etf": False, "dq": "clean", "drift": None}]}
    ok("universe valid", sv.validate(w(d, "universe.json", uni))[0] is True)
    ok("universe member missing t -> fail", sv.validate(w(d, "universe.json", dict(uni, members=[{"sec": "X"}]))) [0] is False)
    ok("universe count non-int -> fail", sv.validate(w(d, "universe.json", dict(uni, count="one")))[0] is False)

# the committed real cik.json must pass its schema
real_cik = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cik.json")
if os.path.exists(real_cik):
    ok("committed cik.json passes schema", sv.validate(real_cik)[0] is True)

print("\n" + ("ALL SCHEMA-VALIDATE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
