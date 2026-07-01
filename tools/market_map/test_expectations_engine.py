"""Planted-structure tests for expectations_engine.py — labeled prediction band from the half-width,
realized range/vol/volume reconciliation, containment, and walk-forward projection accuracy."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expectations_engine as EE

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


def close(a, b, t=1e-3):
    return a is not None and abs(a - b) <= t


# labeled prediction band from half-width
band = EE.expected_band(100.0, 0.05, 0.90)
ok("band half-width % = z*sigma*100", close(band["halfWidthPct"], 1.644854 * 0.05 * 100, 0.01), band["halfWidthPct"])
ok("band brackets price", band["lo"] < 100 < band["hi"])
ok("band labeled prediction + level", band["kind"] == "prediction interval" and band["level"] == 0.90)
ok("band None on bad input", EE.expected_band(0, 0.05) is None and EE.expected_band(100, 0) is None)

nb = EE.nested_bands(100.0, 0.05, levels=(0.5, 0.8, 0.95))
ok("nested 95% wider than 50%", nb["0.95"]["halfWidthPct"] > nb["0.5"]["halfWidthPct"])

# realized stats
ok("realized close-range %", close(EE.realized_range_pct([100, 110, 90, 95]), 20.0))
ok("realized sigma_H = stdev*sqrt(H)", EE.realized_sigma_H([0.01, -0.01, 0.02, -0.005], 4) > 0)
ok("range None on thin", EE.realized_range_pct([100]) is None)

# ratios + verdicts
ok("ratio", close(EE._ratio(1.5, 1.0), 1.5))
ok("verdict expanded/quiet/as-expected", EE._verdict(1.5) == "expanded" and EE._verdict(0.5) == "quiet" and EE._verdict(1.0) == "as expected")

# reconcile: outcome inside band
rec = EE.reconcile(100.0, 0.05, 0.90, [100, 105, 110, 95, 103], [0.02, -0.01, -0.05, 0.03], [1e6, 1.2e6, 9e5], 8e5, 103.0)
ok("reconcile has range/vol/volume/containment", all(k in rec for k in ("range", "vol", "volume", "containment")))
ok("reconcile inside band (103 in [92,108])", rec["containment"]["inside"] is True)
ok("reconcile actual range % present", rec["range"]["actualPct"] is not None)
ok("reconcile volume ratio present", rec["volume"]["ratio"] is not None)
# reconcile: outcome breaches band
rec2 = EE.reconcile(100.0, 0.05, 0.90, [100, 130], [0.26], [1e6], 8e5, 130.0)
ok("reconcile breach -> inside False", rec2["containment"]["inside"] is False)
ok("reconcile breach -> range expanded", rec2["range"]["verdict"] == "expanded")

# walk-forward accuracy on a random walk with volume
rng = random.Random(9)
c = [100.0]; v = []
for _ in range(400):
    c.append(c[-1] * math.exp(rng.gauss(0, 0.01))); v.append(1e6 * math.exp(rng.gauss(0, 0.3)))
v.append(1e6)
acc = EE.accuracy(c, v, H=21, level=0.90, stride=3)
ok("accuracy produced", acc is not None and acc["n"] > 0)
ok("RW containment near 0.90", 0.78 <= acc["containment"] <= 0.99, acc["containment"])
ok("accuracy reports mean ratios", acc["meanRangeRatio"] is not None and acc["meanVolRatio"] is not None and acc["meanVolumeRatio"] is not None)
ok("thin history -> None", EE.accuracy(c[:50], v[:50]) is None)

print("\nALL expectations_engine PASS" if not fail else "\nSOME expectations_engine TESTS FAILED")
sys.exit(1 if fail else 0)
