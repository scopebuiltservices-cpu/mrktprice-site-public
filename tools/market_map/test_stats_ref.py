#!/usr/bin/env python3
"""Planted-structure tests for stats_ref.py (the Python ADF/KPSS reference). Also (re)generates the
cross-language golden fixture tools/stats_golden.json that test_stats_parity.mjs checks the dashboard
JS against — so the "verified vs Python" claim is a real passing test (code-review H1). Run: python3 test_stats_ref.py"""
import os, sys, json, random, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stats_ref as sr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

def ar1(n, phi, sd, seed):
    rng = random.Random(seed); x = 0.0; out = []
    for _ in range(n):
        x = phi * x + rng.gauss(0, sd); out.append(x)
    return out

def random_walk(n, sd, seed):
    rng = random.Random(seed); x = 0.0; out = []
    for _ in range(n):
        x += rng.gauss(0, sd); out.append(x)
    return out

# 1) ADF: a STATIONARY AR(1) (phi=0.2) should reject the unit root; a RANDOM WALK should not
stat = ar1(300, 0.2, 1.0, 7)
walk = random_walk(300, 1.0, 9)
a_stat = sr.adf(stat); a_walk = sr.adf(walk)
ok("ADF rejects unit root on stationary AR(1)", a_stat["reject"] is True, a_stat)
ok("ADF does NOT reject on a random walk", a_walk["reject"] is False, a_walk)
ok("ADF tstat more negative for stationary than RW", a_stat["tstat"] < a_walk["tstat"], (a_stat["tstat"], a_walk["tstat"]))
ok("MacKinnon 5% cv in the expected range", -3.1 < a_stat["cv5"] < -2.6, a_stat["cv5"])

# 2) KPSS as a hypothesis test: LOW rejection of stationary white noise (size), HIGH rejection of a
#    strong trend (power). A single stationary realization can exceed the cv ~5% of the time, so a
#    one-shot "does not reject" is unreliable — test the RATES over many seeds instead.
def white(n, seed):
    rng = random.Random(seed); return [rng.gauss(0, 1) for _ in range(n)]
wn_rej = sum(1 for s in range(40) if sr.kpss(white(250, 200 + s))["reject"]) / 40.0
tr_rej = sum(1 for s in range(40) if sr.kpss([0.05 * i + v for i, v in enumerate(white(250, 300 + s))])["reject"]) / 40.0
ok("KPSS size: rarely rejects stationary white noise (<30%)", wn_rej < 0.30, wn_rej)
ok("KPSS power: almost always rejects a strong trend (>90%)", tr_rej > 0.90, tr_rej)
level = white(300, 11); trend = [0.05 * i + white(300, 13)[i] for i in range(300)]
ok("KPSS eta larger for trend than level", sr.kpss(trend)["eta"] > sr.kpss(level)["eta"])

# 3) OLS recovers a planted linear relationship
X = [[1.0, float(i)] for i in range(50)]; y = [3.0 + 2.0 * i for i in range(50)]
beta, se = sr.ols(X, y)
ok("OLS recovers intercept ~3", abs(beta[0] - 3.0) < 1e-6, beta[0])
ok("OLS recovers slope ~2", abs(beta[1] - 2.0) < 1e-6, beta[1])

# 4) regenerate the golden fixture (series + Python ADF/KPSS) for the JS parity test
fixture = {
    "note": "Golden fixture: terminal.html ADF/KPSS JS must match stats_ref.py on these exact series.",
    "cases": []
}
for name, series in (("stationary_ar1", stat), ("random_walk", walk), ("level", level), ("trend", trend)):
    a = sr.adf(series); k = sr.kpss(series)
    fixture["cases"].append({
        "name": name,
        "series": [round(v, 10) for v in series],
        "adf": {"tstat": a["tstat"], "cv5": a["cv5"], "lag": a["lag"], "reject": a["reject"]},
        "kpss": {"eta": k["eta"], "reject": k["reject"]},
    })
out = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stats_golden.json"))
try:
    with open(out, "w") as fh:
        json.dump(fixture, fh)
    ok("golden fixture written for JS parity", os.path.exists(out))
except Exception as e:
    ok("golden fixture written for JS parity", False, e)

print("\n" + ("ALL STATS-REF TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
