#!/usr/bin/env python3
"""Tests for make_seeds.build_seeds + health refusal (pure). Run: python3 test_make_seeds.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_seeds as MS, sector_integrity as SI

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

secs = list(SI.GICS)
def mm(sectored=40, extra=50, idx=("SPX",)):
    names = [{"t": "EQ%03d" % i, "n": "Co %d" % i, "sec": secs[i % len(secs)], "idx": list(idx)} for i in range(sectored)]
    names += [{"t": "ETF%03d" % i, "sec": "Commodity"} for i in range(extra)]
    d = {"names": names, "sectorCorr": {"order": secs, "m": [[1.0] * len(secs) for _ in secs]}}
    return d

uni, prof = MS.build_seeds(mm(sectored=40))
ok("only equities seeded", len(uni) == 40 and len(prof) == 40, (len(uni), len(prof)))
ok("rows are 4-tuples", all(len(r) == 4 for r in uni))
ok("code mapped from idx", uni[0][3] == "S", uni[0])
ok("profile shape", set(prof[uni[0][0]].keys()) == {"sector", "sectorRaw", "industry", "exchange"})
# membership code mapping for multi-index
u2, _ = MS.build_seeds(mm(sectored=5, idx=("NDX", "SPX", "DOW")))
ok("multi-index code", set(u2[0][3].split()) == {"ND", "S", "D"}, u2[0])
# health refusal: an all-Unknown build yields no equities -> sector_violations fires
bad = mm(sectored=40)
for n in bad["names"]:
    if n["t"].startswith("EQ"): n["sec"] = "Unknown"
ub, pb = MS.build_seeds(bad)
ok("broken build -> no equities", len(ub) == 0)
ok("broken build flagged by gate", len(SI.sector_violations(bad)) > 0)

print("\n" + ("ALL MAKE-SEEDS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
