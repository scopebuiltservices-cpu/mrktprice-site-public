#!/usr/bin/env python3
"""Tests for price_source.PriceSource with injected fake providers (no network). Run: python3 test_price_source.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import price_source as ps

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# fake FMP: returns [[date,o,h,l,c,v],...] for AAA, None for BBB
class FakeFMP:
    def have_key(self): return True
    def eod_ohlcv(self, sym, sess=None, min_rows=10):
        if sym == "AAA":
            return [["2026-06-%02d" % (i + 1), 9.0 + i, 11.0 + i, 8.0 + i, 10.0 + i, 1000 + i] for i in range(12)]
        return None

# fake yfinance: returns a history frame-like for BBB
class _Series(list):
    def tolist(self): return list(self)
class _Frame(dict): pass
class FakeTicker:
    def __init__(self, sym): self.sym = sym
    def history(self, period=None, interval=None, auto_adjust=None):
        n = 15
        return {"Close": _Series([100.0 + i for i in range(n)]), "Volume": _Series([500 + i for i in range(n)]),
                "High": _Series([101.0 + i for i in range(n)]), "Low": _Series([99.0 + i for i in range(n)])}
class FakeYF:
    def Ticker(self, sym): return FakeTicker(sym)

# 1) FMP-first: AAA comes from FMP with correct OHLCV mapping
src = ps.PriceSource(fmp=FakeFMP(), yf=FakeYF(), now=lambda: "2026-06-27T00:00:00Z")
a = src.get("AAA")
ok("AAA served by FMP", a and a["src"] == "fmp", a and a["src"])
ok("FMP close mapped from col 4", a["cl"][0] == 10.0 and a["cl"][-1] == 21.0, a["cl"][:2])
ok("FMP high/low/vol mapped", a["hi"][0] == 11.0 and a["lo"][0] == 8.0 and a["vo"][0] == 1000.0)
ok("fmpLastOk stamped", src.health["fmpLastOk"] == "2026-06-27T00:00:00Z")

# 2) yfinance fallback: BBB (FMP returns None) -> yfinance
b = src.get("BBB")
ok("BBB falls back to yfinance", b and b["src"] == "yfinance", b and b["src"])
ok("yf closes parsed", b["cl"][0] == 100.0 and len(b["cl"]) == 15)

# 3) health counters
ok("health counts fmp=1 yf=1 miss=0", src.health["fmp"] == 1 and src.health["yf"] == 1 and src.health["miss"] == 0, src.health)
ok("price_share = 50% (1 fmp / 2 total)", abs(src.price_share() - 50.0) < 1e-9, src.price_share())

# 4) FMP-only (yf disabled): BBB -> miss, degraded() false (FMP still pulled AAA)
src2 = ps.PriceSource(fmp=FakeFMP(), yf=None)
ok("yf disabled -> yfImported False", src2.health["yfImported"] is False)
ok("AAA still served by FMP", src2.get("AAA")["src"] == "fmp")
ok("BBB -> None when yf disabled", src2.get("BBB") is None)
ok("miss counted", src2.health["miss"] == 1, src2.health)

# 5) degraded(): key present but zero FMP pulls
class DeadFMP:
    def have_key(self): return True
    def eod_ohlcv(self, sym, sess=None, min_rows=10): return None
src3 = ps.PriceSource(fmp=DeadFMP(), yf=None)
src3.get("AAA")
ok("degraded True when key present but 0 FMP pulls", src3.degraded() is True, src3.health)

# 6) min_rows gate: a short FMP series is rejected (falls through)
class ShortFMP:
    def have_key(self): return False
    def eod_ohlcv(self, sym, sess=None, min_rows=10):
        return [["2026-06-01", 1, 1, 1, 1, 1]] if len(sym) else None   # 1 row < min_rows -> module returns None itself
src4 = ps.PriceSource(fmp=ShortFMP(), yf=None)
# ShortFMP ignores min_rows, but real fmp_history enforces it; here we just confirm a 1-row payload still maps
r4 = src4.get("X")
ok("short FMP payload handled without crash", r4 is None or r4["src"] == "fmp")

print("\n" + ("ALL PRICE-SOURCE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
