#!/usr/bin/env python3
"""Tests for contract_drift.py — declared-vs-emitted contract auditing. Run: python3 test_contract_drift.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract_drift as cd

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

SCHEMA = {
    "required": ["schemaVersion", "asof", "source", "names"],
    "$defs": {"name": {"required": ["t"],
                       "properties": {"t": {}, "n": {}, "sec": {}, "beta": {}, "lineage": {}}}},
}

def mk(extra_name=None, drop_lineage=False, sv="2.1"):
    rec = {"t": "AAA", "n": "Alpha", "sec": "Tech", "beta": 1.1, "lineage": {"x": 1}}
    if drop_lineage:
        rec.pop("lineage")
    if extra_name:
        rec.update(extra_name)
    return {"schemaVersion": sv, "asof": "2026-06-30", "source": "build", "names": [rec, dict(rec, t="BBB")]}

# clean payload -> no errors
e, w, info = cd.audit(mk(), SCHEMA)
ok("clean payload: no errors", e == [], e)
ok("declared emission counted", info["declaredEmission"]["lineage"] == 2, info["declaredEmission"])

# DECLARED field emitted by ZERO names -> ERROR (the conformalPad-class promise-vs-emit drift)
e2, w2, _ = cd.audit(mk(drop_lineage=True), SCHEMA)
ok("declared-but-never-emitted -> ERROR", any("lineage" in x and "promise-vs-emit" in x for x in e2), e2)

# missing required top-level -> ERROR
bad = mk(); del bad["source"]
e3, _, _ = cd.audit(bad, SCHEMA)
ok("missing required top-level -> ERROR", any("source" in x for x in e3), e3)

# missing required per-name -> ERROR
bad2 = mk(); del bad2["names"][0]["t"]
e4, _, _ = cd.audit(bad2, SCHEMA)
ok("missing required per-name -> ERROR", any("required per-name" in x for x in e4), e4)

# undeclared field emitted by majority -> WARN (doc drift), not error
e5, w5, info5 = cd.audit(mk(extra_name={"tbv": 1.2}), SCHEMA)
ok("undeclared majority field -> WARN", any("tbv" in x and "NOT declared" in x for x in w5), w5)
ok("undeclared common field censused", "tbv" in info5["undeclaredCommon"], info5["undeclaredCommon"])
ok("undeclared field is NOT an error", e5 == [], e5)

# malformed schemaVersion -> WARN
_, w6, _ = cd.audit(mk(sv="garbage"), SCHEMA)
ok("malformed schemaVersion -> WARN", any("schemaVersion" in x for x in w6), w6)

print("\n" + ("ALL CONTRACT-DRIFT TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
