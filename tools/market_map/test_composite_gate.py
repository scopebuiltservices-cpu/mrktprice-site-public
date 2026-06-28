#!/usr/bin/env python3
"""Tests for composite_gate, trial_ledger, intraday_conviction against planted structure.
Run: python3 test_composite_gate.py"""
import os, sys, math, tempfile, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import composite_gate as cg
import trial_ledger as tl
import intraday_conviction as ic

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# ===== trial_ledger =====
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "trials.jsonl")
    ok("empty ledger totals to floor 1", tl.totals(p)["total"] == 1)
    tl.record(p, "thresholdGrid", 80, "RVOL grid")
    tl.record(p, "thresholdGrid", 40, "z grid")
    tl.record(p, "factorSubset", 12)
    tl.record(p, "lookback", 5)
    t = tl.totals(p)
    ok("ledger sums all trials", t["total"] == 80 + 40 + 12 + 5, t["total"])
    ok("ledger buckets by category", t["byCategory"]["thresholdGrid"] == 120 and t["byCategory"]["factorSubset"] == 12, t["byCategory"])
    ok("live extra adds to total", tl.totals(p, extra=20)["total"] == 137 + 20)
    ok("unknown category folds to 'other'", tl.record(p, "weird", 3)["category"] == "other")

# ===== composite_gate =====
# planted: a moderately predictive composite (positive-mean IC series). Per-rebalance Sharpe ~1.5-2 so it
# clears DSR at a low honest trial count but DEFLATES under a huge trial count (the PDF's core point).
rng = random.Random(7)
strong = {"a": [0.10 + 0.05 * rng.gauss(0, 1) for _ in range(60)],
          "b": [0.10 + 0.05 * rng.gauss(0, 1) for _ in range(60)]}
w = {"a": 0.6, "b": 0.4}
g = cg.gate(strong, w, horizon=5, n_trials=3, breadth=0.8)
ok("strong composite: Sharpe positive", g["compositeSharpe"] is not None and g["compositeSharpe"] > 0, g["compositeSharpe"])
ok("strong composite: DSR high", g["dsr"] is not None and g["dsr"] > 0.9, g["dsr"])
ok("strong composite: passes gate", g["pass"] is True, g)
ok("strong composite: conviction scale 1.0", abs(g["convictionScale"] - 1.0) < 1e-9, g["convictionScale"])

# same signal but a HUGE honest trial count -> DSR collapses -> degrade (PDF's core point)
g2 = cg.gate(strong, w, horizon=5, n_trials=100000, breadth=0.8)
ok("massive trial count deflates DSR", g2["dsr"] is not None and g2["dsr"] < g["dsr"], (g["dsr"], g2["dsr"]))
ok("deflated composite degrades conviction (<1)", g2["convictionScale"] < 1.0, g2["convictionScale"])

# zero-mean noise composite -> ~0.5 DSR, should not pass
noise = {"a": [0.0 + 0.05 * rng.gauss(0, 1) for _ in range(60)],
         "b": [0.0 + 0.05 * rng.gauss(0, 1) for _ in range(60)]}
g3 = cg.gate(noise, w, horizon=5, n_trials=50, breadth=0.8)
ok("noise composite fails the gate", g3["pass"] is False, g3)

# thin breadth degrades conviction even with decent DSR
g4 = cg.gate(strong, w, horizon=5, n_trials=3, breadth=0.10)
ok("thin breadth degrades conviction", g4["convictionScale"] < 1.0, g4["convictionScale"])

# composite_series math: C_t = Σ w_f IC_{f,t}
cs = cg.composite_series({"a": [1.0, 2.0], "b": [10.0, 20.0]}, {"a": 1.0, "b": 0.5})
ok("composite series weights correctly", cs == [1.0 + 5.0, 2.0 + 10.0], cs)

# ===== intraday_conviction =====
# planted long flip: all four core gates pass
m = {"rvol": 2.34, "z": 2.41, "vwap_reclaim": True, "obv_t": 2.27, "mfi": 83, "breakout_atr": 1.18}
r = ic.evaluate(m, side="long")
ok("long flip fires when all core gates pass", r["flip"] is True, r["row"])
ok("row publishes value AND cutoff", "RVOL 2.34≥2.00" in r["row"] and "≥2.00" in r["row"], r["row"])
ok("row shows VWAP reclaim YES", "VWAP reclaim YES" in r["row"], r["row"])
ok("row shows OBV t-stat", "OBV slope t=+2.27≥2.00" in r["row"], r["row"])
ok("row shows MFI + breakout confirmations", "MFI 83≥80" in r["row"] and "Breakout +1.18 ATR≥1.00" in r["row"], r["row"])

# one core gate fails -> no flip, failed comparator still shown
m2 = dict(m, rvol=1.4)
r2 = ic.evaluate(m2, side="long")
ok("long flip blocked when RVOL below cutoff", r2["flip"] is False, r2["row"])
ok("failed comparator still displayed", "RVOL 1.40≥2.00" in r2["row"], r2["row"])

# short side mirrors the signs
ms = {"rvol": 2.5, "z": -2.6, "vwap_reclaim": False, "obv_t": -2.4}
rs = ic.evaluate(ms, side="short")
ok("short flip fires on sign-reversed gates", rs["flip"] is True, rs["row"])
ok("short VWAP loss displayed", "VWAP loss" in rs["row"], rs["row"])

# estimators
ok("sigma_tod displacement = (P-VWAP)/sig", abs(ic.sigma_tod_displacement(102, 100, 1.0) - 2.0) < 1e-9)
ok("breakout/ATR = (P-level)/atr", abs(ic.breakout_atr(105, 100, 2.5) - 2.0) < 1e-9)
# OBV slope t: a clean rising line has a large positive t-stat
ok("OBV slope t positive on rising line", ic.obv_slope_t([1, 2, 3, 4, 5, 6, 7, 8]) > 5)
ok("OBV slope t negative on falling line", ic.obv_slope_t([8, 7, 6, 5, 4, 3, 2, 1]) < -5)

print("\n" + ("ALL COMPOSITE-GATE/LEDGER/CONVICTION TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
