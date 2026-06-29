#!/usr/bin/env python3
"""Tests for deploy_staleness.evaluate (pure). Run: python3 test_deploy_staleness.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deploy_staleness as DS

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# repo newer than live by 3 days -> stale
r = DS.evaluate("2026-06-29", "2026-06-26", max_lag_days=1)
ok("live 3 days behind repo -> stale", r["stale"] and r["lagDays"] == 3, r)

# same day -> in sync
r = DS.evaluate("2026-06-29", "2026-06-29", max_lag_days=1)
ok("same asof -> not stale", (not r["stale"]) and r["lagDays"] == 0, r)

# one day behind, tolerance 1 -> not stale
r = DS.evaluate("2026-06-29", "2026-06-28", max_lag_days=1)
ok("1 day behind within tolerance -> ok", not r["stale"], r)

# live AHEAD of repo (e.g. repo checkout slightly behind) -> negative lag, not stale
r = DS.evaluate("2026-06-28", "2026-06-29", max_lag_days=1)
ok("live ahead of repo -> not stale", (not r["stale"]) and r["lagDays"] == -1, r)

# unparseable -> indeterminate, not stale
r = DS.evaluate("2026-06-29", "never", max_lag_days=1)
ok("unparseable live -> indeterminate", (not r["stale"]) and r["lagDays"] is None, r)

# lag_days helper
ok("lag_days basic", DS.lag_days("2026-06-29", "2026-06-27") == 2)
ok("lag_days unparseable -> None", DS.lag_days("x", "2026-06-27") is None)

print("\n" + ("ALL DEPLOY-STALENESS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
