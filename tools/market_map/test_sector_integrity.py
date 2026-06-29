#!/usr/bin/env python3
"""Tests for sector_integrity (pure). Run: python3 test_sector_integrity.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sector_integrity as SI

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

secs = list(SI.GICS)
def build(sectored=40, corr=True, extra=50):
    names = [{"t": "EQ%03d" % i, "sec": secs[i % len(secs)]} for i in range(sectored)]
    names += [{"t": "ETF%03d" % i, "sec": "Commodity"} for i in range(extra)]
    d = {"names": names}
    if corr: d["sectorCorr"] = {"order": secs, "m": [[1.0] * len(secs) for _ in secs]}
    return d

ok("healthy: no violations", SI.sector_violations(build()) == [])
ok("sectored count excludes ETFs", SI.sectored_equities(build(sectored=40)["names"]) == 40)
allunknown = build(); 
for n in allunknown["names"]:
    if n["t"].startswith("EQ"): n["sec"] = "Unknown"
ok("all-Unknown -> collapse violation", any("sector collapse" in v for v in SI.sector_violations(allunknown)))
nocorr = build(corr=True); nocorr["sectorCorr"] = {"order": [], "m": []}
ok("empty corr -> violation", any("sectorCorr empty" in v for v in SI.sector_violations(nocorr)))
ok("regression: 93 vs 150 blocks", SI.regression_violation(build(40, extra=53)["names"], build(90, extra=60)["names"]) is not None)
ok("regression: mild shrink ok", SI.regression_violation(build(60, extra=60)["names"], build(90, extra=60)["names"]) is None)
ok("summary shape", set(SI.summary(build()).keys()) == {"names", "sectoredEquities", "sectorCorrEmpty", "asof"})

print("\n" + ("ALL SECTOR-INTEGRITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
