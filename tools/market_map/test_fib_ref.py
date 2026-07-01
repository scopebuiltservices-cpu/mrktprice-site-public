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
ok("fib preset", FB.horizons("fib") == [1, 2, 3, 5, 8, 13, 21, 34, 55])
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

# ---- report-driven improvements ----
ok("fib preset is the full 1..55 lattice", FB.horizons("fib") == [1, 2, 3, 5, 8, 13, 21, 34, 55])
us = FB.user_subset(FB.project(closes[-1], 0.001, closes, [1, 2, 5, 21]))
ok("user_subset maps 24H/48H/1W/1M", us["24H"]["H"] == 1 and us["1W"]["H"] == 5 and us["1M"]["H"] == 21)

# sigma decomposition
ok("sigma_total combines process+model+event", abs(FB.sigma_total(0.03, 0.04, 0.12) - math.sqrt(0.03**2 + 0.04**2 + 0.12**2)) < 1e-12)
ok("sigma_total process-only == process", FB.sigma_total(0.05) == 0.05)

# direct-forecast path overrides the fallback + flags source
pd = FB.project(closes[-1], 0.001, closes, [5, 21], mu_by_H={5: 0.07})
ok("direct mu used + source=direct", pd[0]["source"] == "direct" and abs(pd[0]["muLog"] - 0.07) < 1e-12)
ok("non-direct horizon falls back", pd[1]["source"] == "fallback")

# daily edge cap
pc = FB.project(closes[-1], 0.5, closes, [1], cap_daily=1.5)[0]
sd_dbg = FB.blended_sigma_daily(FB._logret(closes))
ok("daily edge cap clamps the 1-session drift", abs(pc["muLog"]) <= 1.5 * sd_dbg + 1e-9)

# zEdge present
ok("projection carries zEdge", "zEdge" in pd[0])

# expected-path maturity consistency: path at e=H equals the stored horizon target
s0 = 100.0; muH = 0.05; hlx = 3.0
ok("expected_path_price(.,H) == target at maturity", abs(FB.expected_path_price(s0, muH, hlx, 5, 5) - s0 * math.exp(muH)) < 1e-9)
ok("expected_path_price(.,0) ~ s0", abs(FB.expected_path_price(s0, muH, hlx, 0, 5) - s0) < 1e-9)

# deviation + dual-condition anti-deviation
dv = FB.deviation(101.0, 100.0, 0.02)
ok("deviation gapLog sign", dv["gapLog"] > 0 and dv["zDeviation"] > 0)
ok("anti_dev reverting when both improve", FB.anti_deviation(0.05, 0.02, 2.0, 1.0)["state"] == "reverting")
ok("anti_dev diverging when both worsen", FB.anti_deviation(0.02, 0.05, 1.0, 2.0)["state"] == "diverging")
ok("anti_dev stable when mixed (denominator artifact)", FB.anti_deviation(0.05, 0.02, 1.0, 2.0)["state"] == "stable")

# probability tile
ok("prob_above > 0.5 for positive drift", FB.prob_above(100.0, 0.05, 0.05, 100.0) > 0.5)
ok("prob_above < 0.5 for high threshold", FB.prob_above(100.0, 0.0, 0.05, 110.0) < 0.5)

# aggregate skill / MASE
sk = FB.skill_mase([0.01, 0.012, 0.009], [0.03, 0.028, 0.031])
ok("skill_mase > 0 when model beats naive", sk["skill"] > 0 and sk["mase"] < 1)

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
