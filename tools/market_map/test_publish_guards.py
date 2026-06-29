#!/usr/bin/env python3
"""Tests for publish_guards.evaluate (pure; no files/network). Run: python3 test_publish_guards.py"""
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_guards as PG
import sector_integrity as SI

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

TODAY = dt.date.today().isoformat()
SECS = list(SI.GICS)

def healthy(n_names=90, sectored=40, with_corr=True):
    names = []
    for i in range(sectored):
        names.append({"t": "EQ%03d" % i, "sec": SECS[i % len(SECS)],
                      "val": {"pe": 20.0}})
    for i in range(n_names - sectored):           # ETFs / macro (no GICS sector)
        names.append({"t": "ETF%03d" % i, "sec": "Commodity"})
    d = {"asof": TODAY, "source": "FMP+yfinance", "names": names}
    if with_corr:
        d["sectorCorr"] = {"order": SECS, "m": [[1.0] * len(SECS) for _ in SECS]}
    return d

# 1) healthy build passes
e, w, s = PG.evaluate(healthy())
ok("healthy build: no core errors", e == [], e)
ok("healthy build: sectored counted", s["sectoredEquities"] == 40)

# 2) sector collapse (every equity 'Unknown') blocks
bad = healthy(); 
for nme in bad["names"]:
    if nme["t"].startswith("EQ"): nme["sec"] = "Unknown"
e, w, s = PG.evaluate(bad)
ok("sector collapse blocks", any("sector collapse" in x for x in e), e)

# 3) empty sectorCorr (but sectors present) blocks
nocorr = healthy(with_corr=True); nocorr["sectorCorr"] = {"order": [], "m": []}
e, w, s = PG.evaluate(nocorr)
ok("empty sectorCorr blocks", any("sectorCorr empty" in x for x in e), e)

# 4) universe regression vs previous published build blocks
prev = healthy(n_names=150, sectored=90)
small = healthy(n_names=93, sectored=40)   # 93 < 70% of 150 (=105) -> block
e, w, s = PG.evaluate(small, prev=prev)
ok("universe regression blocks", any("universe regression" in x for x in e), e)
# a mild shrink (not >30%) must NOT block on regression grounds
mild = healthy(n_names=120, sectored=60)
e2, _, _ = PG.evaluate(mild, prev=prev)
ok("mild shrink does NOT trip regression", not any("universe regression" in x for x in e2), e2)

# 5) SAMPLE/synthetic + thin + stale still block (unchanged behavior)
e, w, s = PG.evaluate({"asof": TODAY, "source": "SAMPLE synthetic", "names": healthy()["names"]})
ok("SAMPLE source blocks", any("SAMPLE" in x for x in e), e)
e, w, s = PG.evaluate({"asof": TODAY, "source": "FMP", "names": healthy(n_names=20, sectored=20)["names"]})
ok("thin universe blocks", any("thin universe" in x for x in e), e)
old = (dt.date.today() - dt.timedelta(days=9)).isoformat()
e, w, s = PG.evaluate({"asof": old, "source": "FMP", "names": healthy()["names"],
                       "sectorCorr": {"order": SECS, "m": [[1.0]]}})
ok("stale asof blocks", any("stale asof" in x for x in e), e)

# 6) enrichment degradation is a WARNING, never a core error
deg = healthy(); deg["dataHealth"] = {"fmpTried": 100, "fmpOk": 0}
e, w, s = PG.evaluate(deg)
ok("FMP-down is warning not block", e == [] and any("FMP valuations" in x for x in w), (e, w))

print("\n" + ("ALL PUBLISH-GUARD TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
