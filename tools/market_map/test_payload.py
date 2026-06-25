#!/usr/bin/env python3
"""Contract tests: validate_payload accepts the golden fixture and rejects every invariant violation.
The same golden_payload.json drives the consumer (JS) checks, so the two ends can never drift.
Run:  python3 test_payload.py     (exit 0 = all pass)"""
import copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_payload as vp

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = json.load(open(os.path.join(HERE, "golden_payload.json")))
SCHEMA = json.load(open(os.path.join(HERE, "marketmap.schema.json")))
FAILS = []


def check(name, cond):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        FAILS.append(name)


def v(payload):
    return vp.validate_payload(payload, SCHEMA, min_names=1)


ok, errs, warns = v(copy.deepcopy(GOLDEN))
check("golden fixture is accepted (0 errors)", ok and not errs)

# V1 - unsupported major rejected
d = copy.deepcopy(GOLDEN); d["schemaVersion"] = "9.0"
ok, errs, _ = v(d); check("V1 unsupported schemaVersion major rejected", (not ok) and any("V1" in e for e in errs))

# V1 - missing version rejected
d = copy.deepcopy(GOLDEN); del d["schemaVersion"]
ok, errs, _ = v(d); check("V1 missing schemaVersion rejected", not ok)

# V2 - duplicate ticker rejected
d = copy.deepcopy(GOLDEN); d["names"][1]["t"] = "AAPL"
ok, errs, _ = v(d); check("V2 duplicate ticker rejected", (not ok) and any("duplicate" in e for e in errs))

# V2 - missing ticker rejected
d = copy.deepcopy(GOLDEN); d["names"][0].pop("t")
ok, errs, _ = v(d); check("V2 missing ticker rejected", not ok)

# V3 - impossible coverage rejected
d = copy.deepcopy(GOLDEN); d["dataHealth"]["coverage"]["priceOk"] = 99
ok, errs, _ = v(d); check("V3 coverage>universe rejected", (not ok) and any("V3" in e for e in errs))

# V4 - crossed quantile band rejected
d = copy.deepcopy(GOLDEN); d["names"][0]["lineage"]["conformal"]["20d"] = {"lo": 0.07, "hi": -0.08}
ok, errs, _ = v(d); check("V4 crossed band (lo>hi) rejected", (not ok) and any("lo>hi" in e for e in errs))

# V6 - non-finite leaked rejected
d = copy.deepcopy(GOLDEN); d["names"][0]["vol"] = float("inf")
ok, errs, _ = v(d); check("V6 non-finite number rejected", (not ok) and any("V6" in e for e in errs))

# min-names threshold (the real workflow uses 30)
ok, errs, _ = vp.validate_payload(copy.deepcopy(GOLDEN), SCHEMA, min_names=30)
check("V2 min-names=30 threshold fires on a 3-name fixture", not ok)

print("\n" + ("ALL CONTRACT TESTS PASSED" if not FAILS else "%d FAILED: %s" % (len(FAILS), FAILS)))
raise SystemExit(1 if FAILS else 0)
