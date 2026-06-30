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

# --- provenance / audit fields on the per-event contract -------------------------------------------
ne = ec.normalize(raw[0], source="fmp", source_ts="2026-06-27T00:00:00")
for k in ("source", "sourceTimestamp", "timezone", "session", "canonicalId", "revision", "confidence"):
    ok("normalize() carries provenance field '%s'" % k, k in ne, list(ne.keys()))
ok("existing keys preserved", all(k in ne for k in ("date", "event", "impact", "actual", "estimate", "previous")))
ok("source is the passed feed name", ne["source"] == "fmp", ne["source"])
ok("sourceTimestamp is the passed ISO ts", ne["sourceTimestamp"] == "2026-06-27T00:00:00", ne["sourceTimestamp"])
ok("timezone defaults to NY", ne["timezone"] == "America/New_York", ne["timezone"])
ok("session is a string in the allowed set", ne["session"] in ("premarket", "regular", "afterhours", "unknown"), ne["session"])
ok("canonicalId is a 12-hex string", isinstance(ne["canonicalId"], str) and len(ne["canonicalId"]) == 12 and all(c in "0123456789abcdef" for c in ne["canonicalId"]), ne["canonicalId"])
ok("revision is int 0 by default", isinstance(ne["revision"], int) and ne["revision"] == 0, ne["revision"])
ok("confidence is a float in [0,1]", isinstance(ne["confidence"], float) and 0.0 <= ne["confidence"] <= 1.0, ne["confidence"])
ok("confidence 1.0 when actual present (CPI has actual)", ne["confidence"] == 1.0, ne["confidence"])
ok("confidence 0.6 when only estimate", ec.normalize({"date": "2026-07-01", "event": "X", "estimate": "1.0"})["confidence"] == 0.6)
ok("confidence 0.4 for bare date/event", ec.normalize({"date": "2026-07-01", "event": "X"})["confidence"] == 0.4)

# canonicalId determinism + discrimination
id_a1 = ec.normalize(raw[0], source="fmp")["canonicalId"]
id_a2 = ec.normalize(raw[0], source="fmp")["canonicalId"]
id_b = ec.normalize(raw[2], source="fmp")["canonicalId"]
id_a_other_src = ec.normalize(raw[0], source="te")["canonicalId"]
ok("canonicalId stable for same input", id_a1 == id_a2, (id_a1, id_a2))
ok("canonicalId differs for different events", id_a1 != id_b, (id_a1, id_b))
ok("canonicalId differs for different source", id_a1 != id_a_other_src, (id_a1, id_a_other_src))

# session derivation from a row carrying a time
ok("session=regular for a 10:00 event", ec.normalize({"date": "2026-07-01", "event": "X", "time": "10:00"})["session"] == "regular")
ok("session=premarket for an 08:30 event", ec.normalize({"date": "2026-07-01", "event": "X", "time": "08:30"})["session"] == "premarket")

# build_events threads source/source_ts into every event
evp = ec.build_events(raw, today=TODAY, source="fmp", source_ts="2026-06-27T00:00:00")
ok("build_events stamps source on events", evp["nextHighImpact"]["source"] == "fmp", evp["nextHighImpact"])
ok("build_events stamps sourceTimestamp on events", evp["nextHighImpact"]["sourceTimestamp"] == "2026-06-27T00:00:00")

# empty / no-data degrades gracefully
e0 = ec.build_events([], today=TODAY)
ok("empty calendar -> no next event, no crash", e0["nextHighImpact"] is None and e0["daysToNext"] is None)

print("\n" + ("ALL EVENTS-CALENDAR TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
