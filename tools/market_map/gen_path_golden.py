#!/usr/bin/env python3
"""gen_path_golden.py — emit the Python-authoritative golden fixture for path_probability.js parity.
Run: python3 gen_path_golden.py  ->  writes path_probability_golden.json (commit it).
Regenerate + commit whenever path_probability.py's closed forms change."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import path_probability as P

cases = []
for (s, m, b, k) in [(0.20, 0.0, 0.15, 0.05), (0.10, 0.0, 0.08, -0.02), (0.30, 0.10, 0.25, 0.10),
                     (0.15, -0.05, 0.12, 0.0), (0.25, 0.05, 0.20, 0.20), (0.08, 0.0, 0.05, 0.03)]:
    cases.append({
        "in": {"s": s, "m": m, "b": b, "k": k},
        "touchUp": P.touch_up(b, s, m),
        "touchDown": P.touch_down(-abs(b), s, m),
        "eMFE": P.expected_max_favorable(s, m),
        "eMAE": P.expected_max_adverse(s, m),
        "q90": P.running_max_quantile(0.90, s, m),
        "q50": P.running_max_quantile(0.50, s, m),
        "pCond": P.prob_end_above_given_touch_up(abs(b), k, s, m if abs(m) < 1e-15 else 0.0),
    })

reports = []
for (s0, sig, T, bu, bd, lv) in [(100.0, 0.02, 5, 104.0, 97.0, 102.0),
                                 (50.0, 0.015, 10, 53.0, 48.0, 51.0),
                                 (250.0, 0.025, 21, 270.0, 235.0, 255.0)]:
    reports.append({"in": {"s0": s0, "sig": sig, "T": T, "bu": bu, "bd": bd, "lv": lv},
                    "out": P.path_report(s0, sig, T, barrier_up=bu, barrier_dn=bd, level=lv, drift_daily=0.0)})

out = {"schema": "path_probability_golden/1", "cases": cases, "reports": reports}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "path_probability_golden.json")
with open(path, "w") as f:
    json.dump(out, f, indent=1)
print("wrote", path, "-", len(cases), "cases,", len(reports), "reports")
