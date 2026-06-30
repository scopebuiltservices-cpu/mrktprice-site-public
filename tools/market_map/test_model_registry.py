#!/usr/bin/env python3
"""Tests for model_registry.py — append-only, hash-keyed, idempotent build provenance. Run: python3 test_model_registry.py"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_registry as mr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

with tempfile.TemporaryDirectory() as d:
    a1 = os.path.join(d, "marketmap.json"); open(a1, "w").write('{"names":[1,2,3]}')
    a2 = os.path.join(d, "xsection.json"); open(a2, "w").write('{"m":[[1]]}')
    out = os.path.join(d, "model_registry.jsonl")

    e, appended = mr.register(d, ["marketmap.json", "xsection.json", "missing.json"], out)
    ok("entry built with present artifacts only", set(e["artifacts"].keys()) == {"marketmap.json", "xsection.json"}, e["artifacts"])
    ok("first build appended", appended is True)
    ok("each artifact has sha256+bytes", all("sha256" in v and "bytes" in v for v in e["artifacts"].values()), e["artifacts"])
    ok("dataSha is a digest", isinstance(e["dataSha"], str) and len(e["dataSha"]) == 64, e["dataSha"])
    ok("schema tag present", e["schema"] == "modelRegistry/1", e)

    # idempotent: same content -> NOT re-appended
    e2, appended2 = mr.register(d, ["marketmap.json", "xsection.json"], out)
    ok("identical build is idempotent (not re-appended)", appended2 is False, appended2)
    ok("registry still has exactly 1 line", sum(1 for _ in open(out)) == 1)

    # change one artifact -> new dataSha -> appended
    open(a1, "w").write('{"names":[1,2,3,4]}')
    e3, appended3 = mr.register(d, ["marketmap.json", "xsection.json"], out)
    ok("changed data -> new dataSha", e3["dataSha"] != e["dataSha"], (e["dataSha"], e3["dataSha"]))
    ok("changed build appended", appended3 is True)
    ok("registry now has 2 lines", sum(1 for _ in open(out)) == 2)

    # calibration run id threads through (explicit arg)
    e4, _ = mr.register(d, ["marketmap.json"], os.path.join(d, "r2.jsonl"), calib_run_id="run-42")
    ok("calibrationRunId recorded", e4["calibrationRunId"] == "run-42", e4)

    # last_entry reads the final committed entry
    le = mr.last_entry(out)
    ok("last_entry returns the most recent", le["dataSha"] == e3["dataSha"], le)

print("\n" + ("ALL MODEL-REGISTRY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
