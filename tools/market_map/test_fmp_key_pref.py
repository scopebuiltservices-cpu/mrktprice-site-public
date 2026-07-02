#!/usr/bin/env python3
"""Confirm every FMP connector's _key() reads ONLY FMP_ULTIMATE_API_KEY and that the legacy
FMP_API_KEY alias is gone (setting it has no effect). Run: python3 test_fmp_key_pref.py"""
import os, sys, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

MODS = ["fmp_history", "fmp_connector", "fmp_bulk", "fmp_estimates", "fmp_actions",
        "fmp_profile", "fmp_float", "events_calendar"]
for envset in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
    os.environ.pop(envset, None)

# FMP_ULTIMATE_API_KEY is the sole source of truth.
os.environ["FMP_ULTIMATE_API_KEY"] = "ULT"
for m in MODS:
    mod = importlib.import_module(m)
    ok("%s _key reads FMP_ULTIMATE_API_KEY" % m, mod._key() == "ULT", mod._key())

# The legacy alias FMP_API_KEY has been removed: setting it must have NO effect.
os.environ.pop("FMP_ULTIMATE_API_KEY", None)
os.environ["FMP_API_KEY"] = "OLD"
for m in MODS:
    mod = importlib.import_module(m)
    ok("%s ignores legacy FMP_API_KEY (returns empty)" % m, mod._key() == "", mod._key())
os.environ.pop("FMP_API_KEY", None)

print("\n" + ("ALL FMP-KEY-PREF TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
