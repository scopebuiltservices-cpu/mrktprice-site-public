#!/usr/bin/env python3
"""Tests for rate_real multi-source parsers + curve validation (fixtures, no network).
Run: python3 test_rate_sources.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_real as rr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- FRED keyless CSV parser (fredgraph.csv): '.' = missing, only full rows kept ---
fred_csv = "DATE,DFII5,DFII10,DFII30\n2026-06-24,1.85,2.10,2.45\n2026-06-25,.,2.12,2.46\n2026-06-26,1.88,2.13,2.47\n"
rows = rr._parse_fred_csv(fred_csv)
ok("fred csv keeps full rows only", set(rows.keys()) == {"2026-06-24", "2026-06-26"}, list(rows))
ok("fred csv parses values", rows["2026-06-26"]["DFII10"] == 2.13, rows.get("2026-06-26"))

# --- Treasury real par CSV parser: columns '5 YR','10 YR','30 YR' ---
trez = ('"Date","5 YR","7 YR","10 YR","20 YR","30 YR"\n'
        '06/26/2026,1.88,2.01,2.13,2.40,2.47\n'
        '06/25/2026,1.86,2.00,2.12,2.39,2.46\n')
trows = rr._parse_treasury_real(trez)
ok("treasury parses 5/10/30", trows["06/26/2026"][5] == 1.88 and trows["06/26/2026"][30] == 2.47, trows.get("06/26/2026"))
ok("treasury ignores 7/20 YR for L/S/C", set(trows["06/26/2026"].keys()) == {5, 10, 30})

# --- curve validation: plausible passes, implausible/short rejected ---
good = {"dates": ["d%02d" % i for i in range(40)], "y5": [1.8] * 40, "y10": [2.1] * 40, "y30": [2.4] * 40}
ok("valid curve accepted", rr._valid_curve(good) is True)
bad_range = dict(good, y10=[99.0] * 40)
ok("implausible yield (99%) rejected", rr._valid_curve(bad_range) is False)
short = {"dates": ["d0", "d1"], "y5": [1.8, 1.8], "y10": [2.1, 2.1], "y30": [2.4, 2.4]}
ok("short curve rejected (<30)", rr._valid_curve(short) is False)
nan_curve = dict(good, y5=[float("nan")] * 40)
ok("non-finite curve rejected", rr._valid_curve(nan_curve) is False)

# --- L/S/C math: Diebold-Li from 5/10/30 ---
d = rr.lsc(1.8, 2.1, 2.4)
ok("L = (5+10+30)/3", abs(d["L"] - (1.8 + 2.1 + 2.4) / 3) < 1e-9)
ok("S = 30 - 5", abs(d["S"] - (2.4 - 1.8)) < 1e-9)
ok("C = 2*10 - 5 - 30", abs(d["C"] - (2 * 2.1 - 1.8 - 2.4)) < 1e-9)

# --- end-to-end on a validated fixture: curve_state + classify wiring ---
cs = rr.curve_state(good)
ok("curve_state returns L/S/C + dL", cs is not None and "L" in cs and "dL" in cs, cs)

print("\n" + ("ALL RATE-SOURCE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
