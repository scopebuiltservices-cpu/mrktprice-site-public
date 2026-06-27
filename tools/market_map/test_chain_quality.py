#!/usr/bin/env python3
"""Tests for chain_quality conventions/quote-sanity gate (BSM audit data-quality wiring).
Run: python3 test_chain_quality.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain_quality as cq

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

ok("options_conventions wired into chain_quality", cq._oc is not None)

chain = [
    {"strike": 100, "type": "C", "bid": 1.30, "ask": 1.25, "oi": 500, "iv": 0.22},   # crossed -> drop
    {"strike": 105, "type": "C", "bid": 2.00, "ask": 2.00, "oi": 500, "iv": 0.20},   # locked  -> drop
    {"strike": 110, "type": "C", "bid": 0.80, "ask": 0.90, "oi": 500, "iv": 22.0},   # percent IV -> normalize+keep
    {"strike": 95,  "type": "C", "bid": 3.00, "ask": 3.10, "oi": 500, "iv": 0.25},   # clean -> keep
    {"strike": 90,  "type": "C", "bid": 4.00, "ask": 4.10, "oi": 2,   "iv": 0.30},   # thin OI -> liquidity drop
]
g = cq.conventions_gate(chain)
gs = sorted(o["strike"] for o in g)
ok("crossed market dropped", 100 not in gs, gs)
ok("locked market dropped", 105 not in gs, gs)
ok("clean + percent-IV + thin-OI survive gate", gs == [90, 95, 110], gs)
ok("percent IV normalized 22.0 -> 0.22", any(o["strike"] == 110 and abs(o["iv"] - 0.22) < 1e-9 for o in g))
ok("normalized row tagged ivUnitsFixed", any(o["strike"] == 110 and o.get("ivUnitsFixed") for o in g))
ok("decimal IV untouched", any(o["strike"] == 95 and abs(o["iv"] - 0.25) < 1e-9 and not o.get("ivUnitsFixed") for o in g))

# staleness gate when timestamps present
stale = [{"strike": 100, "type": "C", "bid": 1.0, "ask": 1.1, "oi": 500, "ts": 1000}]
ok("stale quote dropped with asof", cq.conventions_gate(stale, asof_ts=2000, max_stale_sec=120) == [])
ok("fresh quote kept with asof", len(cq.conventions_gate(stale, asof_ts=1050, max_stale_sec=120)) == 1)

# liquidity_filter now applies the gate end-to-end
lf = cq.liquidity_filter(chain, min_oi=10)
lfs = sorted(o["strike"] for o in lf)
ok("liquidity_filter excludes crossed+locked+thin", lfs == [95, 110], lfs)
ok("liquidity_filter keeps marks", all(o["mark"] is not None for o in lf))

print("\n" + ("ALL CHAIN-QUALITY GATE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
