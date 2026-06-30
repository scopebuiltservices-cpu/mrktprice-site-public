#!/usr/bin/env python3
"""Tests for needs_rebuild.py — the self-healing rebuild trigger. Run: python3 test_needs_rebuild.py"""
import datetime as dt, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import needs_rebuild as nr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

TODAY = dt.date(2026, 6, 30)
def w(d, obj):
    p = os.path.join(d, "marketmap.json"); json.dump(obj, open(p, "w")); return p

with tempfile.TemporaryDirectory() as d:
    # CURRENT engine, fresh -> no rebuild
    cur = {"asof": "2026-06-30", "source": "Live · FMP Ultimate primary (prices)",
           "dataHealth": {"priceSrc": {"fmp": 90}, "fmpLastOk": "2026-06-30T05:00:00Z"}, "names": [{"t": "AAA"}]}
    need, why = nr.needs_rebuild(w(d, cur), 2, today=TODAY)
    ok("fresh current-engine map -> no rebuild", need is False, why)

    # OLD engine (the live bug): yfinance-primary source + missing FMP-primary health fields -> rebuild
    old = {"asof": "2026-06-30", "source": "Live (yfinance prices + FMP Ultimate rates/commodities)",
           "dataHealth": {"coverage": {"universe": 93}}, "names": [{"t": "AAA"}]}
    need, why = nr.needs_rebuild(w(d, old), 2, today=TODAY)
    ok("OLD-engine (yfinance-primary) map -> rebuild", need is True, why)
    ok("reason names the old engine", "OLDER engine" in why, why)

    # current engine but STALE (>2 days) -> rebuild
    stale = {"asof": "2026-06-27", "source": "Live · FMP Ultimate primary",
             "dataHealth": {"priceSrc": {"fmp": 90}, "fmpLastOk": "2026-06-27T05:00:00Z"}, "names": [{"t": "AAA"}]}
    need, why = nr.needs_rebuild(w(d, stale), 2, today=TODAY)
    ok("3-day-stale map -> rebuild", need is True, why)
    ok("reason names staleness", "stale" in why, why)

    # current engine, exactly at the staleness budget (2 days) -> NO rebuild (boundary)
    edge = {"asof": "2026-06-28", "source": "Live · FMP Ultimate primary",
            "dataHealth": {"priceSrc": {"fmp": 90}, "fmpLastOk": "x"}, "names": [{"t": "AAA"}]}
    need, why = nr.needs_rebuild(w(d, edge), 2, today=TODAY)
    ok("exactly 2 days old -> no rebuild (within budget)", need is False, why)

    # missing dataHealth fields entirely (old engine) even if asof is today -> rebuild
    nohealth = {"asof": "2026-06-30", "source": "Live", "dataHealth": {}, "names": [{"t": "AAA"}]}
    need, why = nr.needs_rebuild(w(d, nohealth), 2, today=TODAY)
    ok("no FMP-primary health fields -> rebuild", need is True, why)

    # missing file -> rebuild
    need, why = nr.needs_rebuild(os.path.join(d, "nope.json"), 2, today=TODAY)
    ok("missing file -> rebuild", need is True, why)

    # unparseable -> rebuild
    bad = os.path.join(d, "bad.json"); open(bad, "w").write("{not json")
    need, why = nr.needs_rebuild(bad, 2, today=TODAY)
    ok("unparseable map -> rebuild", need is True, why)

print("\n" + ("ALL NEEDS-REBUILD TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
