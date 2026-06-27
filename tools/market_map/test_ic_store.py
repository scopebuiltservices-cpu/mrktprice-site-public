#!/usr/bin/env python3
"""Offline tests for ic_store: snapshot idempotency, horizon-gated maturation, IC sign recovery, history.
Run: python3 test_ic_store.py"""
import os, sys, tempfile, shutil, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_store as ics

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

tmp = tempfile.mkdtemp(prefix="ic_")
try:
    snp = os.path.join(tmp, "snap.jsonl"); icp = os.path.join(tmp, "ic.jsonl")
    origin = "2026-01-05"
    # 20 names: "good" factor = rank that will predict fwd return; "noise" factor = unrelated
    rows = []
    for i in range(20):
        rows.append({"t": "T%02d" % i, "px": 100.0, "F": {"good": float(i), "noise": float((i * 7) % 20)}})
    ok("snapshot writes", ics.snapshot(snp, origin, rows) is True)
    ok("snapshot idempotent on asof", ics.snapshot(snp, origin, rows) is False)

    # px_now: forward return increases with the 'good' factor (i) -> good IC should be ~+1
    px_now = {"T%02d" % i: 100.0 * (1.0 + 0.01 * i) for i in range(20)}
    # too early: same-day maturation must NOT fire for a 20-day horizon
    ok("no maturation before horizon", ics.mature(snp, icp, origin, 20, px_now) == 0)
    # at origin+20d: matures once
    asof_now = (datetime.date.fromisoformat(origin) + datetime.timedelta(days=20)).isoformat()
    ok("matures once after horizon", ics.mature(snp, icp, asof_now, 20, px_now) == 1)
    ok("maturation is idempotent", ics.mature(snp, icp, asof_now, 20, px_now) == 0)

    hist = ics.read_history(icp, 20)
    ok("history has both factors", "good" in hist and "noise" in hist, list(hist.keys()))
    ok("good factor IC ~ +1 (predicted fwd return)", hist["good"][0] > 0.95, hist.get("good"))
    ok("noise factor IC near 0", abs(hist["noise"][0]) < 0.5, hist.get("noise"))

    # second origin to confirm history accumulates in order
    o2 = (datetime.date.fromisoformat(origin) + datetime.timedelta(days=21)).isoformat()
    ics.snapshot(snp, o2, rows)
    a2 = (datetime.date.fromisoformat(o2) + datetime.timedelta(days=20)).isoformat()
    ics.mature(snp, icp, a2, 20, px_now)
    ok("history accumulates (2 points for good)", len(ics.read_history(icp, 20)["good"]) == 2, ics.read_history(icp,20)["good"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL IC-STORE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
