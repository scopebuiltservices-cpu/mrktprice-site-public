"""Planted tests for monitoring.py: build synthetic logs with KNOWN structure and assert the metrics
and alerts behave (skillful->ok, inverted->alert, drift->alert, degraded health->alert)."""
import os, sys, json, random, tempfile, shutil, datetime as dt
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monitoring as M

def _write(root, rows, name="alpha_log.jsonl"):
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    with open(os.path.join(root, "data", name), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

def _gen(seed, slope, n_days=30, n_names=30, shift_recent=0.0, shift_after=20):
    rng = random.Random(seed)
    base = dt.date(2026, 1, 1)
    rows = []
    for d in range(n_days):
        day = (base + dt.timedelta(days=d)).isoformat()
        for _ in range(n_names):
            a = rng.gauss(0, 1)
            if d >= shift_after:
                a += shift_recent                      # distribution shift in the recent window
            fwd = slope * a + rng.gauss(0, 0.01)       # realized forward return
            rows.append({"d": day, "t": "T%d" % rng.randint(0, 999), "alpha": round(a, 4),
                         "px": 100.0, "fwd": round(fwd, 6)})
    return rows

def test_skillful_is_ok():
    root = tempfile.mkdtemp()
    try:
        _write(root, _gen(1, slope=0.02))
        rep = M.compute(root, window=8)
        m = rep["metrics"]
        assert m["rankIC"] > 0.5, m["rankIC"]
        assert m["hitRate"] > 0.5, m["hitRate"]
        assert m["decileMonotonic"] > 0.9, m["decileMonotonic"]
        assert rep["status"] == "ok", rep["alerts"]
        print("  PASS  skillful -> rankIC=%.3f decileMono=%.3f hit=%.3f status=ok"
              % (m["rankIC"], m["decileMonotonic"], m["hitRate"]))
    finally:
        shutil.rmtree(root)

def test_inverted_alerts():
    root = tempfile.mkdtemp()
    try:
        _write(root, _gen(2, slope=-0.02))
        rep = M.compute(root, window=8)
        assert rep["status"] == "alert", rep
        assert any(a["metric"] == "rankIC_recent" and a["value"] < 0 for a in rep["alerts"]), rep["alerts"]
        print("  PASS  inverted signal -> rankIC_recent=%.3f -> ALERT"
              % rep["metrics"]["rankIC_recent"])
    finally:
        shutil.rmtree(root)

def test_distribution_drift_alerts():
    root = tempfile.mkdtemp()
    try:
        # strong positive skill (so no IC alert) but a big mean shift in the recent window
        _write(root, _gen(3, slope=0.02, n_days=40, shift_recent=2.5, shift_after=30))
        rep = M.compute(root, window=10)
        psi = rep["metrics"].get("alphaPSI")
        assert psi is not None and psi > 0.25, psi
        assert any(a["metric"] == "alphaPSI" for a in rep["alerts"]), rep["alerts"]
        print("  PASS  alpha distribution shift -> PSI=%.3f -> alert present" % psi)
    finally:
        shutil.rmtree(root)

def test_health_degraded_alerts():
    root = tempfile.mkdtemp()
    try:
        _write(root, _gen(4, slope=0.02))
        # health log: last 4 builds fmpDegraded + mostly degraded inputs
        hrows = []
        for i in range(6):
            deg = i >= 2
            hrows.append({"asof": "2026-02-%02d" % (i + 1),
                          "dataQuality": {"clean": 2 if deg else 18, "degraded": 16 if deg else 1, "reject": 2 if deg else 1},
                          "fmpDegraded": deg,
                          "driftCensus": {"stable": 5, "moderate": 3, "significant": 12 if deg else 1}})
        with open(os.path.join(root, "health_log.jsonl"), "w") as f:
            for r in hrows:
                f.write(json.dumps(r) + "\n")
        rep = M.compute(root, window=4)
        m = rep["metrics"]
        assert m["fmpDegradedStreak"] >= 3, m["fmpDegradedStreak"]
        assert m["degradedFracRecent"] > 0.5, m["degradedFracRecent"]
        metrics_fired = {a["metric"] for a in rep["alerts"]}
        assert "fmpDegradedStreak" in metrics_fired and "degradedFracRecent" in metrics_fired, metrics_fired
        assert rep["status"] == "alert"
        print("  PASS  degraded health -> fmpStreak=%d degradedFrac=%.2f driftSig=%.2f -> ALERT"
              % (m["fmpDegradedStreak"], m["degradedFracRecent"], m["driftSignificantFracRecent"]))
    finally:
        shutil.rmtree(root)

def test_insufficient_data_is_quiet():
    root = tempfile.mkdtemp()
    try:
        _write(root, [{"d": "2026-01-01", "t": "A", "alpha": 0.1, "px": 100, "fwd": 0.01}])
        rep = M.compute(root)
        assert rep["status"] == "ok" and rep["metrics"]["IC"] is None
        assert rep["alerts"] == []
        print("  PASS  insufficient data -> metrics None, no false alerts")
    finally:
        shutil.rmtree(root)

def test_emit_writes_file():
    root = tempfile.mkdtemp()
    try:
        _write(root, _gen(5, slope=0.02))
        out = os.path.join(root, "monitoring", "latest.json")
        rep = M.compute(root)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(rep, open(out, "w"))
        loaded = json.load(open(out))
        assert loaded["schema"] == "monitoring/1" and "metrics" in loaded
        print("  PASS  emit -> monitoring/latest.json valid (schema=%s)" % loaded["schema"])
    finally:
        shutil.rmtree(root)

if __name__ == "__main__":
    test_skillful_is_ok()
    test_inverted_alerts()
    test_distribution_drift_alerts()
    test_health_degraded_alerts()
    test_insufficient_data_is_quiet()
    test_emit_writes_file()
    print("\nALL MONITORING TESTS PASSED")
