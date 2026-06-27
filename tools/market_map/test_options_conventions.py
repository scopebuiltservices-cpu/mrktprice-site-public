#!/usr/bin/env python3
"""Tests for options_conventions.py — conventions registry + data-quality gate (BSM audit controls).
Run: python3 test_options_conventions.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import options_conventions as oc

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# registry single-source-of-truth
ok("conventions versioned", oc.CONVENTIONS["version"] == "1.0")
ok("day-count ACT/365F -> 365", oc.CONVENTIONS["annualization"] == 365.0)
ok("years_from_days uses 365", abs(oc.years_from_days(365) - 1.0) < 1e-12)
ok("years_from_days floors at 0", oc.years_from_days(-5) == 0.0)
ok("single-name equity -> american", oc.style_for("equity") == "american")
ok("index -> european", oc.style_for("index") == "european")

# BSM input positivity gate
ok("clean inputs pass", oc.bsm_input_gate(100, 100, 1.0, 0.2, 0.05, 0.0)[0])
ok("negative spot rejected", "S_nonpositive" in oc.bsm_input_gate(-1, 100, 1, 0.2)[1])
ok("zero strike rejected", "K_nonpositive" in oc.bsm_input_gate(100, 0, 1, 0.2)[1])
ok("negative T rejected", "T_nonpositive" in oc.bsm_input_gate(100, 100, -1, 0.2)[1])
ok("T==0 allowed (expiry)", oc.bsm_input_gate(100, 100, 0.0, 0.2)[0])
ok("nan sigma rejected", "sigma_not_finite" in oc.bsm_input_gate(100, 100, 1, float("nan"))[1])

# quote gate: the audit's data-quality table
ok("clean quote passes", oc.quote_gate({"bid": 1.20, "ask": 1.25, "sigma": 0.22})["ok"])
ok("clean quote mid", abs(oc.quote_gate({"bid": 1.2, "ask": 1.3})["mid"] - 1.25) < 1e-12)
ok("crossed market rejected", "crossed_market" in oc.quote_gate({"bid": 1.3, "ask": 1.25})["rejects"])
ok("locked market rejected", "locked_market" in oc.quote_gate({"bid": 1.25, "ask": 1.25})["rejects"])
ok("negative quote rejected", "negative_quote" in oc.quote_gate({"bid": -0.1, "ask": 0.2})["rejects"])
ok("percent IV caught", "iv_units_look_like_percent" in oc.quote_gate({"bid": 1, "ask": 1.1, "sigma": 22.0})["rejects"])
ok("decimal IV ok", oc.quote_gate({"bid": 1, "ask": 1.1, "sigma": 0.22})["ok"])
# staleness
ok("stale quote rejected", "stale_quote" in oc.quote_gate({"bid": 1, "ask": 1.1, "ts": 1000}, asof_ts=2000, max_stale_sec=120)["rejects"])
ok("fresh quote ok", oc.quote_gate({"bid": 1, "ask": 1.1, "ts": 1990}, asof_ts=2000, max_stale_sec=120)["ok"])
ok("future timestamp rejected", "future_timestamp" in oc.quote_gate({"bid": 1, "ask": 1.1, "ts": 3000}, asof_ts=2000)["rejects"])
# exercise-style coherence
ok("euro style on equity rejected", "exercise_style_mismatch" in oc.quote_gate({"bid": 1, "ask": 1.1, "style": "european", "underlying_kind": "equity"})["rejects"])
ok("american on equity ok", oc.quote_gate({"bid": 1, "ask": 1.1, "style": "american", "underlying_kind": "equity"})["ok"])
# contract adjustment sanity
ok("nonstandard multiplier flagged", "nonstandard_multiplier_unflagged" in oc.quote_gate({"bid": 1, "ask": 1.1, "multiplier": 50})["rejects"])
ok("adjusted multiplier accepted", oc.quote_gate({"bid": 1, "ask": 1.1, "multiplier": 50, "adjusted": True})["ok"])
# curve coverage
ok("curve covers maturity", oc.curve_coverage_ok([0.25, 1, 2, 5, 10, 30], 2.0)[0])
ok("curve short of maturity flagged", not oc.curve_coverage_ok([0.25, 1, 2], 5.0)[0])
ok("empty curve fails", not oc.curve_coverage_ok([], 1.0)[0])

print("\n" + ("ALL OPTIONS-CONVENTIONS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
