#!/usr/bin/env python3
"""test_tangible_book.py — TANGIBLE BOOK VALUE computation in fundamentals_board.fund_for.

TBVPS = (equity - goodwill - intangibles)/shares. We verify: P/TBV from our own close, the
premium/discount %, the intangible "air" (book - tangible book), and the honest flags for a stock
trading BELOW tangible book (asset-backed margin of safety) vs one with NEGATIVE tangible equity
(goodwill/intangible-heavy — no asset floor). Run: python3 test_tangible_book.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fundamentals_board as fb

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- trading BELOW tangible book: close 8 vs TBVPS 10 -> P/TBV 0.8, 20% discount, asset-backed -----
out = fb.fund_for({"tbvps": 10.0, "bvps": 12.0, "pTbvFmp": 0.81}, None, None, 8.0)
ok("tbvps surfaced", out.get("tbvps") == 10.0, out)
ok("intangible air = book - tangible", out.get("intangPerSh") == 2.0, out)        # 12 - 10
ok("P/TBV from our close", abs(out.get("pTbv") - 0.8) < 1e-9, out)                 # 8/10
ok("discount-to-TBV negative", out.get("tbvDiscPct") == -20.0, out)               # (0.8-1)*100
ok("below-TBV flagged", out.get("tbvFlag") == "below_tbv", out)
ok("vendor P/TBV cross-check kept", out.get("pTbvFmp") == 0.81, out)

# --- premium to tangible book: close 30 vs TBVPS 10 -> P/TBV 3.0, +200% premium, NOT flagged -------
out2 = fb.fund_for({"tbvps": 10.0, "bvps": 11.0}, None, None, 30.0)
ok("premium P/TBV", abs(out2.get("pTbv") - 3.0) < 1e-9, out2)
ok("premium-to-TBV positive", out2.get("tbvDiscPct") == 200.0, out2)
ok("not below-TBV (flag None)", out2.get("tbvFlag") is None, out2)

# --- NEGATIVE tangible equity: TBVPS <= 0 -> pTbv null, flagged negative_tbv (honest, not hidden) ---
out3 = fb.fund_for({"tbvps": -4.5, "bvps": 6.0}, None, None, 25.0)
ok("negative tangible book -> pTbv null", out3.get("pTbv") is None, out3)
ok("negative tangible book flagged", out3.get("tbvFlag") == "negative_tbv", out3)
ok("tbvps still surfaced (negative shown honestly)", out3.get("tbvps") == -4.5, out3)

# --- no tangible data -> no TBV keys (graceful) -----------------------------------------------------
out4 = fb.fund_for({"pe": 18.0, "pb": 3.1}, None, None, 50.0)
ok("no tbvps -> no pTbv key", "pTbv" not in out4 and "tbvps" not in out4, out4)
ok("other fundamentals still pass through", out4.get("pe") == 18.0, out4)

# --- tbvps present but no close -> tbvps/air kept, no price-derived ratio --------------------------
out5 = fb.fund_for({"tbvps": 7.0, "bvps": 9.0}, None, None, None)
ok("tbvps kept without close", out5.get("tbvps") == 7.0 and out5.get("intangPerSh") == 2.0, out5)
ok("no pTbv without close", "pTbv" not in out5, out5)

print("\n" + ("ALL TANGIBLE-BOOK TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
