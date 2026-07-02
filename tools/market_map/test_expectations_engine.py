"""Planted-structure tests for expectations_engine.py (corrected estimands):
  - labeled endpoint prediction band + containment
  - range compared to the MODEL's expected path range (MFE+MAE, discrete-corrected) -> ratio ~1 on GBM
  - volatility scored with QLIKE (=0 on a perfect forecast, robust otherwise)
  - volume as a robust log-space z (sign + magnitude), independent of the half-width
"""
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


# labeled endpoint prediction band
band = EE.expected_band(100.0, 0.05, 0.90)
ok("band half-width % = z*sigma*100", close(band["halfWidthPct"], 1.644854 * 0.05 * 100, 0.01))
ok("band labeled prediction + level", band["kind"] == "prediction interval" and band["level"] == 0.90)

# expected path range uses MFE+MAE (discrete-corrected), NOT the endpoint band
sH = 0.05
elr = EE.expected_log_range(sH, 21, 0.0)
mfe = 0.0  # continuous driftless MFE+MAE = sH*sqrt(8/pi)
cont = sH * math.sqrt(8.0 / math.pi)
ok("expected log range < continuous MFE+MAE (discrete correction applied)", elr < cont and elr > 0.6 * cont, (elr, cont))

# CENTERING: on pure GBM the mean range ratio should sit near 1 (not the ~0.85 of the naive method)
rng = random.Random(2)
c = [100.0]; v = []
for _ in range(600):
    c.append(c[-1] * math.exp(rng.gauss(0, 0.012))); v.append(1e6 * math.exp(rng.gauss(0, 0.3)))
v.append(1e6)
acc = EE.accuracy(c, v, H=21, level=0.90, stride=2)
ok("accuracy produced", acc is not None and acc["n"] > 0)
ok("RW containment near 0.90", 0.80 <= acc["containment"] <= 0.99, acc["containment"])
ok("accuracy reports qlike", acc["qlike"] is not None and acc["qlike"] >= 0)
# CENTERING: isolate the estimand fix from sigma-estimation noise by feeding the TRUE sigma.
# The corrected MFE/MAE+discrete reference centres the range ratio at ~1 (the naive endpoint-band
# method was structurally stuck at ~0.47 — a different estimand).
accT = EE.accuracy(c, v, H=21, level=0.90, stride=2, sigma_fn=lambda cl, h: 0.012 * math.sqrt(h))
ok("range ratio centred near 1 with true sigma (naive method was ~0.47)", 0.88 <= accT["meanRangeRatio"] <= 1.18, accT["meanRangeRatio"])

# QLIKE = 0 when the forecast variance equals the realized variance (perfect)
import vol_loss
ok("qlike zero on perfect forecast", close(vol_loss.qlike([0.04], [0.04]), 0.0))
ok("qlike positive when forecast wrong", vol_loss.qlike([0.04], [0.09]) > 0)

# reconcile: range ratio near 1 on a planted window with the right sigma
base = EE.vol_baseline([1e6, 1.1e6, 9e5, 1.2e6, 8e5])
rets = [rng.gauss(0, 0.012) for _ in range(21)]
win = [100.0]
for r in rets:
    win.append(win[-1] * math.exp(r))
rec = EE.reconcile(win[0], 0.012 * math.sqrt(21), 0.90, win, rets, [1e6] * 22, base, win[-1])
ok("reconcile range ratio present + finite", rec["range"]["ratio"] is not None and rec["range"]["ratio"] > 0)
ok("reconcile vol has qlike + realizedVar", rec["vol"]["qlike"] is not None and rec["vol"]["realizedVar"] > 0)

# volume log-z: an elevated window reads z>0 / 'elevated'; a light window z<0
base2 = EE.vol_baseline([1e6] * 40)
rec_hi = EE.reconcile(100.0, 0.05, 0.90, [100, 101], [0.01], [5e6, 5e6], base2, 101.0)
ok("high volume -> z>0 & elevated", rec_hi["volume"]["z"] > 1.5 and rec_hi["volume"]["verdict"] == "elevated", rec_hi["volume"])
rec_lo = EE.reconcile(100.0, 0.05, 0.90, [100, 101], [0.01], [2e5, 2e5], base2, 101.0)
ok("low volume -> z<0 & light", rec_lo["volume"]["z"] < -1.5 and rec_lo["volume"]["verdict"] == "light", rec_lo["volume"])
ok("volume independent of half-width (uses baseline)", rec_hi["volume"]["rvol"] > 1)

# containment breach
ok("breach -> inside False", EE.reconcile(100.0, 0.05, 0.90, [100, 130], [0.26], [1e6], base2, 130.0)["containment"]["inside"] is False)

# path_projection: dispersion + persistence -> % on the expected path + expected top price/volume
# trending name (VR>1) with volume that rises with |move|
rng3 = random.Random(9)
ct = [100.0]; e = 0.0; vt = []
for _ in range(700):
    e = 0.6 * e + 0.4 * rng3.gauss(0, 1); step = 0.010 * e
    ct.append(ct[-1] * math.exp(step)); vt.append(1e6 * math.exp(2.0 * abs(step) / 0.010 + rng3.gauss(0, 0.2)))
vt.append(vt[-1])
pj = EE.path_projection(ct, vt, H=21)
ok("projection produced", pj is not None)
ok("pathPct is a realistic probability (50-72%)", pj is not None and 50.0 <= pj["pathPct"] <= 72.0, pj and pj["pathPct"])
ok("trending -> smart True (VR significant)", pj is not None and pj["smart"] is True)
ok("expected top price on the expected side", pj is not None and ((pj["dir"] > 0 and pj["peakPrice"] > ct[-1]) or (pj["dir"] < 0 and pj["peakPrice"] < ct[-1])), pj and (pj["dir"], pj["peakPrice"], ct[-1]))
ok("time-to-peak within horizon", pj is not None and 1.0 <= pj["timeToPeakD"] <= 21.0, pj and pj["timeToPeakD"])
ok("volume elasticity engaged -> top volume > median", pj is not None and pj["volElastOK"] is True and pj["topVolMult"] > 1.0, pj and (pj["volElastOK"], pj["topVolMult"]))
# random walk -> not smart, path ~ coin-flip, peak suppressed by caller via smart flag
rng4 = random.Random(21); crw = [100.0]
for _ in range(600):
    crw.append(crw[-1] * math.exp(rng4.gauss(0, 0.012)))
pj2 = EE.path_projection(crw, None, H=21)
ok("random walk -> smart False", pj2 is not None and pj2["smart"] is False, pj2 and pj2["smart"])
ok("random walk pathPct near 50%", pj2 is not None and 49.0 <= pj2["pathPct"] <= 56.0, pj2 and pj2["pathPct"])
ok("projection None on thin history", EE.path_projection(ct[:40]) is None)

# gating
ok("expected_log_range None on bad sigma", EE.expected_log_range(0, 21) is None)
ok("thin accuracy -> None", EE.accuracy(c[:50], v[:50]) is None)

print("\nALL expectations_engine PASS" if not fail else "\nSOME expectations_engine TESTS FAILED")
sys.exit(1 if fail else 0)
