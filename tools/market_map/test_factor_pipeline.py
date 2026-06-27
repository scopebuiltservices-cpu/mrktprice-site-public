#!/usr/bin/env python3
"""Offline tests for factor_pipeline: calculus factors, prior-degrade vs fitted mode, snapshot wiring.
Run: python3 test_factor_pipeline.py"""
import os, sys, tempfile, shutil, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factor_pipeline as fp

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) velocity/acceleration: a steadily rising series -> positive velocity
rise = [100.0 * (1.0 + 0.004) ** i for i in range(60)]
vel, acc = fp.velocity_accel(rise)
ok("velocity positive on uptrend", vel is not None and vel > 0, vel)
ok("acceleration finite", acc is not None and math.isfinite(acc), acc)
ok("short series -> None", fp.velocity_accel([1, 2, 3]) == (None, None))

# 2) accumulation: up days on high volume -> positive; mixed -> near 0
cl = [100 + i for i in range(40)]; vol = [1000] * 40
ok("all-up accumulation = +1", abs(fp.accumulation(cl, vol, 20) - 1.0) < 1e-9, fp.accumulation(cl, vol, 20))
cl2 = [100 + (1 if i % 2 == 0 else -1) for i in range(40)]
ok("alternating accumulation ~ 0", abs(fp.accumulation(cl2, vol, 20)) < 0.2, fp.accumulation(cl2, vol, 20))

# 3) run(): with no history it DEGRADES to labeled priors and still emits per-name calculus
def isetf(t): return t in ("SPY", "QQQ")
names = []
random.seed(5)
for i in range(25):
    c = [50.0]
    for _ in range(80): c.append(c[-1] * (1 + random.gauss(0.0005, 0.01)))
    names.append({"t": "T%02d" % i, "_cl": c, "_vol": [1e6] * len(c),
                  "ret": {"1m": random.gauss(0, 5)}, "flow": {"net1m": random.gauss(0, 0.1), "net3m": random.gauss(0, 0.1)},
                  "secRel": random.gauss(0, 1), "opp": random.gauss(0, 1), "ema21sig": random.gauss(0, 1),
                  "short": {"level": "low", "trend": "flat"}})
names.append({"t": "SPY", "_cl": [400.0] * 90, "_vol": [1e6] * 90})  # ETF excluded
tmp = tempfile.mkdtemp(prefix="fp_")
try:
    out = fp.run(names, tmp, is_etf=isetf)
    ok("degrades to priors with no history", out["factorMode"] == "priors", out["factorMode"])
    ok("emits a full weight vector", abs(sum(abs(v) for v in out["factorWeights"].values()) - sum(abs(v) for v in fp.PRIORS.values())) < 1e-6)
    ok("per-name calculus emitted (ex-ETF)", "T00" in out["calc"] and "SPY" not in out["calc"], list(out["calc"].keys())[:3])
    ok("calc carries vel/acc/acc20/40/63", all(k in out["calc"]["T00"] for k in ("vel", "acc", "acc20", "acc40", "acc63")))
    # snapshot file was written
    ok("snapshot store created", os.path.exists(os.path.join(tmp, "factor_snapshots.jsonl")))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL FACTOR-PIPELINE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
