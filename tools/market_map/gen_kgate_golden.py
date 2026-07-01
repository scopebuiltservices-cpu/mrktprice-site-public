#!/usr/bin/env python3
"""gen_kgate_golden.py — Python-authoritative golden fixture for kolmogorov_gate.js parity.
Stores the exact input arrays + Python outputs so JS is checked on identical data.
Run: python3 gen_kgate_golden.py  ->  kolmogorov_gate_golden.json (commit it)."""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kolmogorov_gate import dual_gate, ks_two_sample

random.seed(20260701)
series = {
    "stationary": [random.gauss(0, 0.01) for _ in range(400)],
    "voljump": [random.gauss(0, 0.01) for _ in range(340)] + [random.gauss(0, 0.03) for _ in range(60)],
    "meanshift": [random.gauss(0, 0.01) for _ in range(340)] + [random.gauss(0.05, 0.01) for _ in range(60)],
    "thin": [random.gauss(0, 0.01) for _ in range(40)],
}
gates = {k: dual_gate(v) for k, v in series.items()}

ks_cases = []
for a, b in [([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]), ([1, 2, 3], [10, 11, 12]),
             (series["stationary"][:120], series["stationary"][-60:])]:
    D, p, ne = ks_two_sample(a, b)
    ks_cases.append({"a": a, "b": b, "D": D, "p": p, "ne": ne})

out = {"schema": "kgate_golden/1", "series": series, "gates": gates, "ksCases": ks_cases}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kolmogorov_gate_golden.json")
with open(path, "w") as f:
    json.dump(out, f)
print("wrote", path, "-", len(series), "series,", len(ks_cases), "ks cases")
