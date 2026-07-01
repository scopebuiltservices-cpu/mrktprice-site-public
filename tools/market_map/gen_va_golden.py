#!/usr/bin/env python3
"""gen_va_golden.py — Python-authoritative golden fixture for volatility_arbiter.js parity.
Run: python3 gen_va_golden.py -> va_golden.json (commit it)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import volatility_arbiter as VA

C = VA.component
cases = [
    {"name": "equal", "physical": [["hv", 0.02, 1.0, 1.0, True], ["ewma", 0.02, 1.0, 1.0, True]], "kw": {}},
    {"name": "relwt", "physical": [["a", 0.01, 1.0, 1.0, True], ["b", 0.03, 0.0, 1.0, True]], "kw": {}},
    {"name": "basewt", "physical": [["a", 0.01, 1.0, 3.0, True], ["b", 0.03, 1.0, 1.0, True]], "kw": {}},
    {"name": "vr_full", "physical": [["hv", 0.02, 1.0, 1.0, True]], "kw": {"sigma_vr": 0.05, "vr_reliability": 1.0}},
    {"name": "vr_half", "physical": [["hv", 0.02, 1.0, 1.0, True], ["ewma", 0.03, 0.8, 1.0, True]],
     "kw": {"sigma_vr": 0.05, "vr_reliability": 0.4}},
    {"name": "evtjump", "physical": [["hv", 0.02, 1.0, 1.0, True]], "kw": {"event_sigma": 0.01, "jump_sigma": 0.005}},
    {"name": "mixed", "physical": [["hv", 0.018, 0.9, 2.0, True], ["ewma", 0.025, 0.7, 1.0, True],
                                   ["harq", 0.03, 0.5, 1.0, True], ["off", 0.09, 1.0, 1.0, False]],
     "kw": {"sigma_vr": 0.04, "vr_reliability": 0.3, "event_sigma": 0.006, "jump_sigma": 0.004}},
]

out = {"schema": "va_golden/1", "cases": []}
for c in cases:
    comps = [C(*p) for p in c["physical"]]
    r = VA.blend(comps, **c["kw"])
    out["cases"].append({"name": c["name"], "physical": c["physical"], "kw": c["kw"],
                         "sigma": r["sigma"], "sigma2": r["sigma2"], "weights": r["weights"],
                         "reliability": r["reliability"]})

vrl = [[2.0, 300, 60, 0.5], [1.0, 300, 60, 0.5], [3.0, 120, 60, 0.5], [2.0, 30, 60, 0.5]]
out["vrLambda"] = [{"args": a, "val": VA.vr_lambda(*a)} for a in vrl]

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "va_golden.json")
json.dump(out, open(path, "w"))
print("wrote", path, "-", len(out["cases"]), "cases,", len(out["vrLambda"]), "vrLambda")
