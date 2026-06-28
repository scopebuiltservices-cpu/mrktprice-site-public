#!/usr/bin/env python3
"""Tests for data_quality.py against planted skew/drift/breakage. Run: python3 test_data_quality.py"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_quality as dq

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

rng = random.Random(11)

# clean series -> verdict clean
clean = [100.0]
for _ in range(120):
    clean.append(clean[-1] * math.exp(0.0003 + 0.01 * rng.gauss(0, 1)))
h = dq.series_health(clean)
ok("clean series verdict clean", h["verdict"] == "clean", h)
ok("clean series no NaN / non-pos", h["nNaN"] == 0 and h["nNonPos"] == 0)

# non-finite + non-positive -> reject
bad = clean[:60] + [float("nan"), -5.0, 0.0] + clean[60:]
hb = dq.series_health(bad)
ok("non-finite+nonpos -> reject", hb["verdict"] == "reject", hb)
ok("counts the NaN", hb["nNaN"] >= 1 and hb["nNonPos"] >= 1)

# stale/stuck feed -> flagged
stale = clean[:60] + [clean[60]] * 6 + clean[66:]
hs = dq.series_health(stale)
ok("stale run detected", hs["staleRun"] >= 6, hs["staleRun"])
ok("stale -> degraded or reject", hs["verdict"] in ("degraded", "reject"))

# MAD jump outliers (a few wild ticks) -> degraded, jumpOutliers>0
spk = list(clean); spk[80] = spk[80] * 1.5; spk[90] = spk[90] * 0.6
hj = dq.series_health(spk)
ok("jump outliers detected", hj["jumpOutliers"] >= 2, hj["jumpOutliers"])

# robust_z flags the planted spike, ignores bulk
z = dq.robust_z([0.0]*20 + [10.0])
ok("robust_z flags spike (|z|>3.5)", abs(z[-1]) > 3.5, z[-1])
ok("robust_z leaves bulk near 0", all(abs(zi) < 1 for zi in z[:20]))

# winsorize clips tails, keeps middle
w = dq.winsorize([ -100 ] + [1.0]*50 + [100], p=0.05)
ok("winsorize clips extreme low", min(w) > -100)
ok("winsorize clips extreme high", max(w) < 100)

# cross-source agreement: identical -> agree; shifted 10% -> disagree
a = clean[-30:]; b = list(a)
ok("identical sources agree", dq.cross_source_agree(a, b)["agree"] is True)
bshift = [x * 1.10 for x in a]
ok("10% shifted sources disagree", dq.cross_source_agree(a, bshift, tol=0.02)["agree"] is False)

# PSI / KS drift: same distribution -> stable; shifted+scaled -> significant
ref = [rng.gauss(0, 1) for _ in range(500)]
cur_same = [rng.gauss(0, 1) for _ in range(300)]
cur_drift = [rng.gauss(1.5, 2.0) for _ in range(300)]
ok("PSI stable on same dist", dq.drift_report(ref, cur_same)["level"] in ("stable", "moderate"), dq.drift_report(ref, cur_same))
ok("PSI significant on shifted dist", dq.drift_report(ref, cur_drift)["level"] == "significant", dq.drift_report(ref, cur_drift))
ok("KS larger for drift than same", (dq.ks_stat(ref, cur_drift) or 0) > (dq.ks_stat(ref, cur_same) or 0))

# guard: finite+in-bounds passes; NaN/inf/out-of-range -> None + reason
v, r = dq.guard(0.5, 0.0, 1.0, "beta"); ok("guard passes valid", v == 0.5 and r is None)
v, r = dq.guard(float("nan"), name="x"); ok("guard rejects NaN", v is None and "non-finite" in r)
v, r = dq.guard(5.0, 0.0, 1.0, "p"); ok("guard rejects out-of-range", v is None and ">" in r)
v, r = dq.guard("abc"); ok("guard rejects non-numeric", v is None and "numeric" in r)

print("\n" + ("ALL DATA-QUALITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
