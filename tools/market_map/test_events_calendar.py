#!/usr/bin/env python3
"""Tests for events_calendar.py (filter + build, no network). Run: python3 test_events_calendar.py"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import events_calendar as ec

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

raw = [
    {"date": "2026-06-25", "country": "US", "impact": "High", "event": "CPI y/y", "actual": "3.1", "estimate": "3.2", "previous": "3.3"},
    {"date": "2026-06-30", "country": "US", "impact": "Low", "event": "FOMC Press Conference", "previous": ""},   # key-pattern despite Low tag
    {"date": "2026-07-03", "currency": "USD", "impact": "High", "event": "Nonfarm Payrolls", "previous": "150K"},
    {"date": "2026-06-26", "country": "DE", "impact": "High", "event": "German IFO"},                            # non-US -> excluded
    {"date": "2026-06-27", "country": "US", "impact": "Low", "event": "Baker Hughes Rig Count"},                 # low + not key -> excluded
]
TODAY = datetime.date(2026, 6, 27)

ok("CPI high-impact US kept", ec.is_high_impact(raw[0]) is True)
ok("FOMC kept via name pattern despite Low tag", ec.is_high_impact(raw[1]) is True)
ok("USD Nonfarm kept", ec.is_high_impact(raw[2]) is True)
ok("non-US event excluded", ec.is_high_impact(raw[3]) is False)
ok("low+non-key event excluded", ec.is_high_impact(raw[4]) is False)

ev = ec.build_events(raw, today=TODAY)
ok("next high-impact is the soonest upcoming (FOMC 06-30)", ev["nextHighImpact"]["event"] == "FOMC Press Conference", ev["nextHighImpact"])
ok("daysToNext computed", ev["daysToNext"] == 3, ev["daysToNext"])
ok("upcoming sorted ascending", [e["date"] for e in ev["upcoming"]] == ["2026-06-30", "2026-07-03"], ev["upcoming"])
ok("recent holds the past CPI", any(e["event"] == "CPI y/y" for e in ev["recent"]), ev["recent"])
ok("upcoming excludes non-US / low-impact", all("German" not in e["event"] and "Rig" not in e["event"] for e in ev["upcoming"]))

# empty / no-data degrades gracefully
e0 = ec.build_events([], today=TODAY)
ok("empty calendar -> no next event, no crash", e0["nextHighImpact"] is None and e0["daysToNext"] is None)

print("\n" + ("ALL EVENTS-CALENDAR TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
