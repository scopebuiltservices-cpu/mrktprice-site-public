#!/usr/bin/env python3
"""Offline tests for alpaca_options: OCC-symbol parsing + key-gating + snapshot normalisation.
No network — the chain fetch is monkeypatched. Run: python3 test_alpaca_options.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alpaca_options as ao

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) OCC symbol parsing: ROOT + YYMMDD + C/P + strike*1000
s, cp, exp = ao._parse_occ("AAPL250117C00150000")
ok("OCC call strike 150.0", s == 150.0 and cp == "C", (s, cp))
ok("OCC expiry parsed 2025-01-17", exp is not None and exp.isoformat() == "2025-01-17", exp)
s2, cp2, _ = ao._parse_occ("SPY251219P00420500")
ok("OCC put strike 420.5", s2 == 420.5 and cp2 == "P", (s2, cp2))
s3, cp3, e3 = ao._parse_occ("not-an-occ")
ok("garbage symbol -> (None,None,None)", s3 is None and cp3 is None and e3 is None)

# 2) key-gating: no creds -> enrich_options returns None (self-skip, no network)
for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"):
    os.environ.pop(k, None)
ok("no keys -> enrich_options None", ao.enrich_options("AAPL", 150.0, [149, 150, 151]) is None)

# 3) snapshot normalisation: monkeypatch _fetch_chain, prove BS summary populates with IV+greeks
os.environ["ALPACA_API_KEY_ID"] = "x"; os.environ["ALPACA_API_SECRET_KEY"] = "y"
def _fake_chain(ticker, kid, ksec, spot, sess):
    chain = []
    for K in (140, 145, 150, 155, 160):
        for cp in ("C", "P"):
            chain.append({"strike": float(K), "type": cp, "oi": 500, "iv": 0.30,
                          "gamma": 0.02, "delta": (0.5 if cp == "C" else -0.5),
                          "bid": 2.0, "ask": 2.2, "last": 2.1, "exp": "2025-12-19", "dte": 30})
    return chain, 30
ao._fetch_chain = _fake_chain
closes = [150 + (i % 5) - 2 for i in range(60)]
res = ao.enrich_options("AAPL", 150.0, closes)
ok("enrich returns dict with bs", isinstance(res, dict) and res.get("bs") is not None, res)
ok("bs summary has ATM IV", res and res["bs"].get("atmIVpct") is not None, res and res.get("bs"))
ok("bs summary tags optSource=alpaca", res and str(res["bs"].get("optSource", "")).startswith("alpaca"), res and res.get("bs"))
ok("GEX computed when OI present", res and res.get("gex") is not None)

print("\n" + ("ALL ALPACA-OPTIONS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
