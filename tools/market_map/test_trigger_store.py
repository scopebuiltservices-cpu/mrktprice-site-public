#!/usr/bin/env python3
"""Offline tests for trigger_store: metric computation, horizon-gated maturation, pooled outcomes feeding
threshold_calib. Run: python3 test_trigger_store.py"""
import os, sys, tempfile, shutil, datetime, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trigger_store as ts, threshold_calib as tc

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) metrics_for: rising series on rising volume -> positive z, OBV-t, velocity; rvol present
cl = [100 * (1.005) ** i for i in range(60)]; vol = [1e6 + 1e4 * i for i in range(60)]
m = ts.metrics_for(cl, vol)
ok("metrics computed", m is not None and all(k in m for k in ("rvol", "z", "obvt", "vel", "px")), m)
ok("uptrend -> z>0, obvt>0, vel>0", m["z"] > 0 and m["obvt"] > 0 and m["vel"] > 0, m)
ok("short series -> None", ts.metrics_for([1, 2, 3], [1, 1, 1]) is None)

tmp = tempfile.mkdtemp(prefix="ts_")
try:
    snp = os.path.join(tmp, "trig_snap.jsonl"); outp = os.path.join(tmp, "trig_out.jsonl")
    origin = "2026-01-05"
    # 30 names: metric 'z' planted to predict forward return; forward px set accordingly
    rows = []; pxnow = {}
    random.seed(1)
    for i in range(30):
        zval = (i - 15) / 5.0
        rows.append({"t": "T%02d" % i, "m": {"rvol": 1.0 + i * 0.1, "z": zval, "obvt": random.gauss(0, 1), "vel": 0.0, "px": 100.0}})
        pxnow["T%02d" % i] = 100.0 * (1.0 + 0.01 * zval)        # fwd return rises with z
    ok("snapshot writes", ts.snapshot(snp, origin, rows) is True)
    ok("snapshot idempotent", ts.snapshot(snp, origin, rows) is False)
    ok("no maturation before horizon", ts.mature(snp, outp, origin, 20, pxnow) == 0)
    asof = (datetime.date.fromisoformat(origin) + datetime.timedelta(days=20)).isoformat()
    ok("matures after horizon", ts.mature(snp, outp, asof, 20, pxnow) == 1)
    ok("mature idempotent", ts.mature(snp, outp, asof, 20, pxnow) == 0)

    zout = ts.read_outcomes(outp, "z")
    ok("pooled z outcomes present", len(zout["values"]) == 30 and len(zout["fwd"]) == 30, len(zout["values"]))
    # threshold_calib should find the z edge (higher z -> higher fwd) in-sample at least
    fit = tc.fit_cutoff(zout["values"], zout["fwd"], [0.0, 1.0, 2.0], min_hits=5, side="ge")
    ok("threshold_calib finds positive-mean cutoff on z", fit is not None and fit["mean"] > 0, fit)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL TRIGGER-STORE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
