#!/usr/bin/env python3
"""Tests for drift_store.py (run-over-run + in-sample drift, persistence). Run: python3 test_drift_store.py"""
import os, sys, json, tempfile, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift_store as ds

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

rng = random.Random(5)
stable = [rng.gauss(0, 0.01) for _ in range(200)]
shifted = [rng.gauss(0.03, 0.03) for _ in range(200)]   # different mean+scale

# in-sample drift: a series that shifts midway is flagged; a homogeneous one is stable
homog = [rng.gauss(0, 0.01) for _ in range(200)]
ok("in-sample stable on homogeneous", ds.in_sample_drift(homog)["level"] in ("stable", "moderate"), ds.in_sample_drift(homog))
jump = [rng.gauss(0, 0.01) for _ in range(120)] + [rng.gauss(0.05, 0.04) for _ in range(120)]
ok("in-sample flags a mid-series regime shift", ds.in_sample_drift(jump)["level"] in ("moderate", "significant"), ds.in_sample_drift(jump))

with tempfile.TemporaryDirectory() as d:
    rp = os.path.join(d, "drift_ref.json"); lp = os.path.join(d, "drift_store.jsonl")
    # run 1: establishes baseline (no run-over-run drift yet), persists reference
    o1 = ds.update(rp, lp, "2026-01-01", {"AAA": stable, "BBB": stable}, ref_lag_days=45)
    ok("run1 sets baseline", o1["AAA"]["status"] == "baseline", o1["AAA"])
    ok("reference persisted to disk", os.path.exists(rp) and "AAA" in ds.load_ref(rp))

    # run 2, same day (ref not aged): AAA fed the SAME dist -> stable; BBB fed a SHIFTED dist -> drift
    o2 = ds.update(rp, lp, "2026-01-02", {"AAA": stable, "BBB": shifted}, ref_lag_days=45)
    ok("run2 measures (not baseline)", o2["AAA"]["status"] == "measured", o2["AAA"])
    ok("stable name -> low drift", o2["AAA"]["level"] in ("stable", "moderate"), o2["AAA"])
    ok("shifted name -> significant drift", o2["BBB"]["level"] == "significant", o2["BBB"])
    ok("drift carries psi + ks", o2["BBB"]["psi"] is not None and o2["BBB"]["ks"] is not None)

    # reference refresh when aged past ref_lag_days
    o3 = ds.update(rp, lp, "2026-04-01", {"AAA": stable, "BBB": shifted}, ref_lag_days=45)  # ~90d later
    ok("aged reference refreshes to baseline", o3["AAA"]["status"] == "baseline", o3["AAA"])
    ok("refreshed refAsof is the new date", ds.load_ref(rp)["AAA"]["asof"] == "2026-04-01")

    # log appended
    lines = [l for l in open(lp).read().splitlines() if l.strip()]
    ok("log appends one record per name per run", len(lines) >= 6, len(lines))
    rec = json.loads(lines[-1]); ok("log record has level + status", "level" in rec and "status" in rec)

    # insufficient data -> labeled, not crashed
    oi = ds.update(rp, lp, "2026-04-02", {"CCC": [0.01, 0.02, 0.03]}, ref_lag_days=45)
    ok("short series labeled insufficient", oi["CCC"]["level"] == "insufficient", oi["CCC"])

    # census
    cen = ds.census(o2)
    ok("census counts levels", cen["significant"] >= 1, cen)
    ok("census flags drifted names", any(f["t"] == "BBB" for f in cen["flagged"]), cen["flagged"])

print("\n" + ("ALL DRIFT-STORE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
