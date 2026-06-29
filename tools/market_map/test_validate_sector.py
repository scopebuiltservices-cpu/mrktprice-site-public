#!/usr/bin/env python3
"""V7/V8 sector+regression invariants in validate_payload. Run: python3 test_validate_sector.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_payload as VP
import sector_integrity as SI

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

SCHEMA = {"required": []}     # structural-only; we are testing the cross-field invariants
secs = list(SI.GICS)
def payload(sectored=40, corr=True, extra=50):
    names = [{"t": "EQ%03d" % i, "sec": secs[i % len(secs)]} for i in range(sectored)]
    names += [{"t": "ETF%03d" % i, "sec": "Commodity"} for i in range(extra)]
    d = {"schemaVersion": "1.0", "names": names}
    if corr: d["sectorCorr"] = {"order": secs, "m": [[1.0] * len(secs) for _ in secs]}
    return d

okk, errs, warns = VP.validate_payload(payload(), SCHEMA, min_names=30)
ok("healthy payload passes", okk, errs)

bad = payload()
for n in bad["names"]:
    if n["t"].startswith("EQ"): n["sec"] = "Unknown"
okk, errs, warns = VP.validate_payload(bad, SCHEMA, min_names=30)
ok("V7 sector collapse fails contract", (not okk) and any(e.startswith("V7") for e in errs), errs)

nocorr = payload(); nocorr["sectorCorr"] = {"order": [], "m": []}
okk, errs, warns = VP.validate_payload(nocorr, SCHEMA, min_names=30)
ok("V7 empty sectorCorr fails contract", any(e.startswith("V7") for e in errs), errs)

prev = payload(sectored=90, extra=60)   # 150 names
small = payload(sectored=40, extra=53)  # 93 names < 70% of 150
okk, errs, warns = VP.validate_payload(small, SCHEMA, min_names=30, prev=prev)
ok("V8 regression fails contract", any(e.startswith("V8") for e in errs), errs)
okk2, errs2, _ = VP.validate_payload(payload(sectored=60, extra=60), SCHEMA, min_names=30, prev=prev)
ok("V8 mild shrink passes", not any(e.startswith("V8") for e in errs2), errs2)

print("\n" + ("ALL VALIDATE-SECTOR TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
