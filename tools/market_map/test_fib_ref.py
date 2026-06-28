#!/usr/bin/env python3
"""Tests for fib_ref.py (Phase 1-2 multi-horizon projection + scoring). Planted-structure + golden-fixture
lock (tools/fib_golden.json) + schema validation of a built record. Run: python3 test_fib_ref.py"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fib_ref as FB

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

def close(a, b, tol=1e-9):
    return a == a and b == b and abs(a - b) <= tol * (1 + abs(b))

# presets
ok("cadence preset", FB.horizons("cadence") == [1, 5, 10, 21, 63])
ok("fib preset", FB.horizons("fib") == [1, 2, 3, 5, 8, 13, 21])
ok("unknown preset -> cadence default", FB.horizons("zzz") == [1, 5, 10, 21, 63])

# decayed edge: hl=1 => r=0.5; H=1 -> edge; H=2 -> edge*1.5
ok("decayed_edge H1 == edge", close(FB.decayed_edge(0.01, 1.0, 1), 0.01))
ok("decayed_edge H2 (r=.5) == 1.5*edge", close(FB.decayed_edge(0.01, 1.0, 2), 0.015))
ok("decayed_edge monotone in H", FB.decayed_edge(0.01, 3.0, 5) > FB.decayed_edge(0.01, 3.0, 2))

# horizon vol: H=1 -> sigma_d; near-random-walk -> ~ sqrt-time
rng = FB._mul32(7); closes = [100.0]
for _ in range(200):
    closes.append(closes[-1] * math.exp(0.013 * (rng() - 0.5)))
rets = FB._logret(closes); sd = FB.blended_sigma_daily(rets)
ok("horizon_sigma H1 == sigma_d", close(FB.horizon_sigma(closes, 1, sd), sd))
ok("horizon_sigma grows with H", FB.horizon_sigma(closes, 10, sd) > FB.horizon_sigma(closes, 2, sd))
ok("near-RW VR~1 => sigma_H ~ sd*sqrt(H) within 35%",
   abs(FB.horizon_sigma(closes, 5, sd) - sd * math.sqrt(5)) < 0.35 * sd * math.sqrt(5))

# blended vol uses ewma + simple (both positive)
ok("blended_sigma_daily positive", sd > 0)

# projection: coherent, bands widen with H (parametric, no resids)
proj = FB.project(closes[-1], 0.001, closes, [1, 5, 21])
ok("projection one row per horizon", [p["H"] for p in proj] == [1, 5, 21])
ok("bands widen with H", (proj[2]["hi"] - proj[2]["lo"]) > (proj[0]["hi"] - proj[0]["lo"]))
ok("parametric band when no resids", all(p["bandMethod"] == "parametric" for p in proj))
ok("projPrice>0 and lo<projPrice<hi", all(p["lo"] < p["projPrice"] < p["hi"] for p in proj))

# conformal band when residuals supplied
resid = {5: [(-1) ** i * 0.01 * (1 + (i % 3)) for i in range(20)]}
projc = FB.project(closes[-1], 0.0, closes, [5], resid_by_H=resid)
ok("conformal band when resids present", projc[0]["bandMethod"] == "conformal")

# calibrated cap: a huge edge gets capped to cap_mult*sigmaH
big = FB.project(closes[-1], 0.5, closes, [5], cap_mult=2.0)[0]
ok("huge edge capped in calibrated units", big["capped"] is True and abs(big["muLog"]) <= 2.0 * big["sigmaH"] + 1e-12)

# scoring + skill-vs-random-walk
pn = 100.0
sc_perfect = FB.score(pn, math.log(110.0), 0.05, 110.0)
ok("perfect forecast: logErr 0, skill 1", close(sc_perfect["logErr"], 0.0) and close(sc_perfect["skillVsRW"], 1.0))
sc_rw = FB.score(pn, math.log(pn), 0.05, 110.0)            # forecast == price_now == random walk
ok("RW-equivalent forecast: skill 0", close(sc_rw["skillVsRW"], 0.0))
ok("direction hit when both up", sc_perfect["dirHit"] == 1)
sc_wrong = FB.score(pn, math.log(95.0), 0.05, 110.0)       # projected down, went up
ok("direction miss flagged", sc_wrong["dirHit"] == 0)

# clustered-miss regime signal
ok("clustered miss: 3 same-sign large", FB.clustered_miss([0.1, 2.0, 2.1, 1.9]) is True)
ok("no clustered miss: mixed sign", FB.clustered_miss([2.0, -2.1, 2.0]) is False)
ok("no clustered miss: small", FB.clustered_miss([0.5, 0.4, 0.3]) is False)

# build_record shape
rec = FB.build_record("2026-06-27", "equity", "cadence", 100.0, proj,
                      ["2026-06-29", "2026-07-06", "2026-07-27"],
                      {"halflife": 3.0, "sigmaDaily": sd})
ok("record has required keys", all(k in rec for k in ("schemaVersion", "asof", "assetClass", "horizonPreset", "priceNow", "params", "horizons")))
ok("record horizons carry targetDate", all("targetDate" in h for h in rec["horizons"]))

# golden-fixture lock
GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fib_golden.json")
if not os.path.exists(GOLD):
    json.dump(FB.gen_fixture(), open(GOLD, "w"), separators=(",", ":"))
g = json.load(open(GOLD)); gi, gx = g["inputs"], g["expected"]
re_proj = FB.project(gi["closes_hist"][-1], gi["edge"], gi["closes_hist"], FB.horizons(gi["preset"]), hl=gx["halflife"])
ok("golden: projection reproduces fixture",
   all(close(re_proj[i]["projLog"], gx["projections"][i]["projLog"]) and close(re_proj[i]["sigmaH"], gx["projections"][i]["sigmaH"]) for i in range(len(re_proj))),
   "projLog/sigmaH mismatch")
re_sc = FB.score(gi["closes_hist"][-1], gx["projections"][0]["projLog"], gx["projections"][0]["sigmaH"], gi["realized_next"])
ok("golden: score reproduces fixture", close(re_sc["skillVsRW"], gx["score_H1"]["skillVsRW"]) and close(re_sc["zErr"], gx["score_H1"]["zErr"]))

# schema validation (skip if jsonschema absent; CI enforces)
try:
    import jsonschema
    from jsonschema import validators
    sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "schemas", "fib_forecast.schema.json")
    schema = json.load(open(sp))
    cls = getattr(jsonschema, "Draft202012Validator", None) or validators.validator_for(schema)
    errs = list(cls(schema).iter_errors(rec))
    ok("built record validates against fib_forecast.schema.json", not errs, errs[:3])
except Exception as e:
    print("  skip  schema validation (%s)" % str(e)[:60])

print("\n" + ("ALL FIB-REF TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
