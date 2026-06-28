#!/usr/bin/env python3
"""Tests for validate_artifacts.py. Run: python3 test_validate_artifacts.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_artifacts as va

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# cik
ok("cik valid", va.validate_cik({"AAPL": "0000320193", "MSFT": "0000789019"})[0])
ok("cik rejects short", not va.validate_cik({"AAPL": "320193"})[0])
ok("cik rejects non-str", not va.validate_cik({"AAPL": 320193})[0])
ok("cik rejects empty", not va.validate_cik({})[0])

# alpha_calib
fb = {"asof": "2026-06-27", "horizonDays": 21, "n": 0, "sigFallback": 9.0, "coef": None,
      "intercept": None, "ic": None, "rankIC": None, "mode": "fallback"}
ok("alpha_calib fallback valid", va.validate_alpha_calib(fb)[0])
fit = dict(fb, mode="fitted", coef=0.5, intercept=0.1, ic=0.08, rankIC=0.07, n=500)
ok("alpha_calib fitted valid", va.validate_alpha_calib(fit)[0])
ok("alpha_calib fitted needs coef/ic", not va.validate_alpha_calib(dict(fb, mode="fitted"))[0])
ok("alpha_calib rejects bad mode", not va.validate_alpha_calib(dict(fb, mode="weird"))[0])
ok("alpha_calib rejects ic>1", not va.validate_alpha_calib(dict(fit, ic=1.5))[0])
ok("alpha_calib rejects missing asof", not va.validate_alpha_calib({k: v for k, v in fb.items() if k != "asof"})[0])

# events
ev = {"asof": "2026-06-27", "schemaVersion": "1.0",
      "nextHighImpact": {"date": "2026-07-01", "event": "CPI"}, "daysToNext": 4,
      "upcoming": [{"date": "2026-07-01", "event": "CPI"}], "recent": [{"date": "2026-06-12", "event": "FOMC"}]}
ok("events valid", va.validate_events(ev)[0])
ok("events null nextHighImpact ok", va.validate_events(dict(ev, nextHighImpact=None, daysToNext=None))[0])
ok("events rejects bad event date", not va.validate_events(dict(ev, upcoming=[{"date": "soon", "event": "x"}]))[0])
ok("events rejects non-list upcoming", not va.validate_events(dict(ev, upcoming="CPI"))[0])
ok("events rejects missing schemaVersion", not va.validate_events({k: v for k, v in ev.items() if k != "schemaVersion"})[0])

# universe
uni = {"asof": "2026-06-27", "schemaVersion": "1.0", "source": "Live", "count": 2, "equities": 1,
       "sectors": {"Technology": 1, "ETF": 1}, "indexMembership": {"SP500": 2},
       "dataQuality": None, "driftCensus": None,
       "members": [{"t": "AAPL", "sec": "Technology", "idx": ["SP500"], "etf": False, "dq": "clean", "drift": None},
                   {"t": "SPY", "sec": "ETF", "idx": ["SP500", "ETF"], "etf": True, "dq": "clean", "drift": None}]}
ok("universe valid", va.validate_universe(uni)[0])
ok("universe rejects count mismatch", not va.validate_universe(dict(uni, count=99))[0])
ok("universe rejects dup ticker", not va.validate_universe(dict(uni, count=2, members=[uni["members"][0], uni["members"][0]]))[0])
ok("universe rejects member w/o ticker", not va.validate_universe(dict(uni, count=2, members=[uni["members"][0], {"sec": "X"}]))[0])

# dispatch by filename + absent-file skip in main()
import tempfile, json
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "cik.json"); json.dump({"AAPL": "0000320193"}, open(p, "w"))
    okd, _ = va.validate_file(p)
    ok("validate_file dispatches by name", okd is True)
    bad = os.path.join(d, "alpha_calib.json"); json.dump({"mode": "weird"}, open(bad, "w"))
    ok("main returns 1 on bad file", va.main([bad]) == 1)
    ok("main skips absent file (rc 0)", va.main([os.path.join(d, "events.json")]) == 0)

print("\n" + ("ALL VALIDATE-ARTIFACTS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
