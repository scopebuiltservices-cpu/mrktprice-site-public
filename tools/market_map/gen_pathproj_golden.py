#!/usr/bin/env python3
"""gen_pathproj_golden.py — deterministic golden for the Py<->JS parity of path_projection.
Writes ../pathproj_golden.json: fixed close+volume series and the Python expectations_engine.path_projection
output. test_pathproj_parity.mjs re-runs path_projection.js on the SAME series and must match. No RNG in
the file (seed baked into a fixed generator), so both languages lock to identical inputs."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expectations_engine as EE
import metrics as M


def _series(kind, n=180):
    # simple LCG so the fixture is language-agnostic and reproducible without importing random
    s = 12345

    def u():
        nonlocal s
        s = (1103515245 * s + 12345) & 0x7fffffff
        return s / 0x7fffffff

    def z():
        return math.sqrt(-2 * math.log(max(u(), 1e-12))) * math.cos(2 * math.pi * u())
    c = [100.0]; v = []; e = 0.0; prev = 0.0
    for _ in range(n):
        if kind == "trend":
            e = 0.6 * e + 0.4 * z(); step = 0.010 * e
        elif kind == "mr":
            step = 0.012 * z() - 0.6 * prev; prev = step
        else:
            step = 0.012 * z()
        c.append(c[-1] * math.exp(step))
        v.append(1e6 * math.exp(1.8 * abs(step) / 0.010 + 0.2 * z()))
    v.append(v[-1])
    return c, v


def main():
    cases = []
    for kind in ("trend", "mr", "rw"):
        c, v = _series(kind)
        cr = [round(x, 6) for x in c]
        hi = [x * 1.01 for x in cr]; lo = [x * 0.99 for x in cr]   # deterministic H/L rule (mirrored in the mjs test)
        cases.append({"kind": kind, "closes": cr, "vols": [round(x, 2) for x in v],
                      "proj": EE.path_projection(c, v, H=21),
                      "vrMulti": M.variance_ratio_multi(c),
                      "championHL": EE._champion_sigma(cr, 21, hi, lo)})   # range-aware (Parkinson) cone sigma, from rounded closes
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pathproj_golden.json")
    json.dump({"fixture_version": 1, "H": 21, "r": 5, "cases": cases}, open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p), "with", len(cases), "cases")


if __name__ == "__main__":
    main()
