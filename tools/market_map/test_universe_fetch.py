#!/usr/bin/env python3
"""Tests for universe_fetch.py (pure parse/merge logic — no network). Run: python3 test_universe_fetch.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import universe_fetch as U

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- screener parse: keep Nasdaq common stocks; drop ETFs/funds, non-Nasdaq, and non-alpha tickers ---
rows = [
    {"symbol": "AAPL", "companyName": "Apple Inc.", "sector": "Technology", "exchangeShortName": "NASDAQ", "marketCap": 3e12},
    {"symbol": "QQQ", "companyName": "Invesco QQQ", "sector": "", "exchangeShortName": "NASDAQ", "isEtf": True},
    {"symbol": "JPM", "companyName": "JPMorgan", "sector": "Financial Services", "exchangeShortName": "NYSE"},  # not Nasdaq
    {"symbol": "ABCDW", "companyName": "Warrant Co WT", "sector": "Tech", "exchangeShortName": "NASDAQ"},        # 5-letter warrant? still alpha<=5 -> kept (acceptable); ensure no crash
    {"symbol": "BRK.B", "companyName": "Berkshire", "sector": "Financial Services", "exchangeShortName": "NASDAQ"},  # dotted -> dropped
]
p = U.parse_screener(rows)
syms = [r[0] for r in p]
ok("screener keeps AAPL", "AAPL" in syms)
ok("screener drops ETF QQQ", "QQQ" not in syms)
ok("screener drops non-Nasdaq JPM", "JPM" not in syms)
ok("screener drops dotted BRK.B", "BRK.B" not in syms)
ok("screener maps sector to canonical", dict((r[0], r[2]) for r in p).get("AAPL") == "Technology")
ok("screener tags ND code", all(r[3] == "ND" for r in p))

# --- nasdaqlisted parse: drop test issues + ETFs ---
txt = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n" \
      "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n" \
      "ZTEST|Nasdaq Test - Common|Q|Y|N|100|N|N\n" \
      "ONEQ|Fidelity Nasdaq ETF|G|N|N|100|Y|N\n" \
      "MSFT|Microsoft Corp - Common|Q|N|N|100|N|N\n" \
      "File Creation Time: 0101\n"
q = U.parse_nasdaqlisted(txt); qs = [r[0] for r in q]
ok("nasdaqlisted keeps AAPL/MSFT", "AAPL" in qs and "MSFT" in qs)
ok("nasdaqlisted drops test issue", "ZTEST" not in qs)
ok("nasdaqlisted drops ETF", "ONEQ" not in qs)
ok("nasdaqlisted ignores footer", "File" not in "".join(qs))

# --- dow merge: tag existing, append missing ---
base = [("AAPL", "Apple", "Technology", "ND"), ("FOO", "Foo", "Tech", "ND")]
m = U._merge_dow(base, ["AAPL", "BA"])
md = dict((r[0], r[3]) for r in m)
ok("dow tags existing AAPL as ND D", "D" in md.get("AAPL", "").split())
ok("dow appends missing BA", "BA" in md and "D" in md["BA"].split())
ok("non-dow FOO unchanged", md.get("FOO") == "ND")

# --- mode gating ---
ok("mode seed -> None", U.fetch_universe("seed", key=None, session=None) is None)
ok("mode unknown -> None", U.fetch_universe("sp500", key=None, session=None) is None)

print("\n" + ("ALL UNIVERSE-FETCH TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
