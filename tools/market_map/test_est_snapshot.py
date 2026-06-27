#!/usr/bin/env python3
"""Offline tests for est_snapshot: idempotent record + revision-drift computation. Run: python3 test_est_snapshot.py"""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import est_snapshot as es

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

tmp = tempfile.mkdtemp(prefix="est_")
try:
    p = os.path.join(tmp, "est_history.jsonl")
    # 1) record writes; same (sym,asof,period) is idempotent
    ok("first record writes", es.record(p, "AAPL", "2026-02-01", "2026-09-30", 7.00, n=30) is True)
    ok("duplicate same day/period skipped", es.record(p, "AAPL", "2026-02-01", "2026-09-30", 7.00, n=30) is False)
    ok("None eps rejected", es.record(p, "AAPL", "2026-02-02", "2026-09-30", None) is False)
    # 2) accumulate a drift series after a report date 2026-02-01
    es.record(p, "AAPL", "2026-02-15", "2026-09-30", 7.10, n=31)
    es.record(p, "AAPL", "2026-03-01", "2026-09-30", 7.35, n=33)
    rev = es.revision(p, "AAPL", "2026-02-01", "2026-09-30")
    ok("revision returns a drift object", isinstance(rev, dict), rev)
    ok("eps0 = first post-report snapshot (7.00)", abs(rev["eps0"] - 7.00) < 1e-9, rev)
    ok("eps1 = latest snapshot (7.35)", abs(rev["eps1"] - 7.35) < 1e-9, rev)
    ok("dPct = +5.0% consensus raise", abs(rev["dPct"] - 5.0) < 0.01, rev)
    # 3) period isolation — a different fiscal period is not mixed in
    es.record(p, "AAPL", "2026-03-02", "2027-09-30", 9.99, n=20)
    rev2 = es.revision(p, "AAPL", "2026-02-01", "2026-09-30")
    ok("other-period snapshot ignored", abs(rev2["eps1"] - 7.35) < 1e-9, rev2)
    # 4) <2 comparable snapshots -> None
    ok("unknown ticker -> None", es.revision(p, "ZZZZ", "2026-02-01") is None)
    ok("since after all snaps -> None", es.revision(p, "AAPL", "2027-01-01", "2026-09-30") is None)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL EST-SNAPSHOT TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
