#!/usr/bin/env python3
"""Tests for the FMP diagnostic layer: the body-aware classifier, the multi-name key reader, and the
classified PRICE-PATH probe. These guard the fix that turns a silent "0 FMP prices -> yfinance" run
into an actionable reason (invalid_key / rate_limited / plan_or_endpoint). Offline (no network)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fmp_connector as C
import fmp_history as H

F = []
def ok(n, c):
    print(("  PASS  " if c else "  FAIL  ") + n)
    if not c:
        F.append(n)

# classify() maps the REAL FMP failure shapes (FMP returns HTTP 200 with an {"Error Message"} body)
ok("invalid key -> invalid_key", C.classify(200, {"Error Message": "Invalid API KEY. Please retry."})[0] == "invalid_key")
ok("HTTP 401 -> invalid_key", C.classify(401, "")[0] == "invalid_key")
ok("limit reach -> rate_limited", C.classify(429, {"Error Message": "Limit Reach . Upgrade your plan"})[0] == "rate_limited")
ok("bandwidth -> rate_limited", C.classify(200, {"Error Message": "You have reached your bandwidth limit"})[0] == "rate_limited")
ok("exclusive/upgrade -> plan_or_endpoint", C.classify(403, {"Error Message": "Exclusive Endpoint: upgrade your plan"})[0] == "plan_or_endpoint")
ok("legacy -> plan_or_endpoint", C.classify(200, {"Error Message": "This is a legacy endpoint"})[0] == "plan_or_endpoint")
ok("good list -> ok", C.classify(200, [{"date": "2026-01-01", "close": 100.0}])[0] == "ok")
ok("empty 200 -> empty", C.classify(200, [])[0] == "empty")

# key reader accepts whichever name the Ultimate secret carries (connector + history must agree)
for k in ("FMP_ULTIMATE_API_KEY", "FMP_API_KEY", "FMP_UTIMATE_API_KEY"):
    os.environ.pop(k, None)
ok("connector _key empty when unset", C._key() == "")
ok("history _key empty when unset", H._key() == "")
os.environ["FMP_ULTIMATE_API_KEY"] = "ZZZ"
ok("connector reads _ULTIMATE variant", C._key() == "ZZZ")
ok("history reads _ULTIMATE variant", H._key() == "ZZZ")
os.environ.pop("FMP_ULTIMATE_API_KEY", None)

# the classified price-path probe exists and reports 'missing' with no key (no network call)
ok("probe_eod in __all__", "probe_eod" in H.__all__)
p = H.probe_eod()
ok("probe_eod no-key -> reason=missing, ok=False", p.get("reason") == "missing" and p.get("ok") is False)

print("\n" + ("ALL FMP-DIAGNOSTIC TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
