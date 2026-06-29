#!/usr/bin/env python3
"""Tests for universe_fetch.py (pure parse/merge/union logic — no network). Run: python3 test_universe_fetch.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import universe_fetch as U

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# --- screener parse ---
rows = [
    {"symbol": "AAPL", "companyName": "Apple Inc.", "sector": "Technology", "exchangeShortName": "NASDAQ"},
    {"symbol": "QQQ", "companyName": "Invesco QQQ", "exchangeShortName": "NASDAQ", "isEtf": True},
    {"symbol": "JPM", "companyName": "JPMorgan", "sector": "Financial Services", "exchangeShortName": "NYSE"},
    {"symbol": "BRK.B", "companyName": "Berkshire", "exchangeShortName": "NASDAQ"},
]
p = U.parse_screener(rows); syms = [r[0] for r in p]
ok("screener keeps AAPL", "AAPL" in syms)
ok("screener drops ETF/NYSE/dotted", not any(s in syms for s in ("QQQ", "JPM", "BRK.B")))
ok("screener maps sector", dict((r[0], r[2]) for r in p).get("AAPL") == "Technology")

c = U.parse_constituent([{"symbol": "JPM", "name": "JPMorgan", "sector": "Financial Services"},
                         {"symbol": "XOM", "name": "Exxon", "sector": "Energy"}], "S")
ok("constituent parses with tag", c == [("JPM", "JPMorgan", "Financials", "S"), ("XOM", "Exxon", "Energy", "S")])

iwm = ("\n\nFund Holdings as of,\nTicker,Name,Sector,Asset Class,Market Value\n"
       "ABCD,Some Small Co,Industrials,Equity,1000\n"
       "WXYZ,Another Co,Health Care,Equity,2000\n")
ri = U.parse_iwm_csv(iwm); rs = [r[0] for r in ri]
ok("IWM parses Russell tickers", "ABCD" in rs and "WXYZ" in rs)
ok("IWM tags R + maps sector", all(r[3] == "R" for r in ri) and dict((r[0], r[2]) for r in ri)["WXYZ"] == "Health Care")

txt = ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
       "AAPL|Apple - Common|Q|N|N|100|N|N\nZTEST|Test|Q|Y|N|100|N|N\nONEQ|ETF|G|N|N|100|Y|N\n")
q = [r[0] for r in U.parse_nasdaqlisted(txt)]
ok("nasdaqlisted keeps AAPL, drops test/ETF", "AAPL" in q and "ZTEST" not in q and "ONEQ" not in q)

# --- four-index UNION with membership tags (small stubs -> set floor low so the collapse guard stays dormant) ---
def _stub_const(session, key, base, stable_ep, v3_ep, tag):
    data = {
        "S": [("AAPL", "Apple", "Technology", "S"), ("JPM", "JPMorgan", "Financials", "S"), ("XOM", "Exxon", "Energy", "S")],
        "D": [("AAPL", "Apple", "Technology", "D"), ("JPM", "JPMorgan", "Financials", "D"), ("CAT", "Caterpillar", "Industrials", "D")],
        "ND": [("AAPL", "Apple", "Technology", "ND")],
    }
    return data.get(tag, [])
_orig = (U.fetch_constituent, U.fetch_screener_rows, U.fetch_iwm_holdings, U.fetch_nasdaqtrader)
U.fetch_constituent = _stub_const
U.fetch_screener_rows = lambda *a, **k: [{"symbol": "AAPL", "companyName": "Apple", "sector": "Technology", "exchangeShortName": "NASDAQ"},
                                         {"symbol": "TSLA", "companyName": "Tesla", "sector": "Consumer Cyclical", "exchangeShortName": "NASDAQ"}]
U.fetch_iwm_holdings = lambda *a, **k: [("SMLL", "Small Co", "Industrials", "R"), ("TINY", "Tiny Co", "Energy", "R")]
U.fetch_nasdaqtrader = lambda *a, **k: []
os.environ["UNIVERSE_MIN"] = "3"   # dormant guard for these intentionally-tiny stub unions
try:
    u = U.fetch_universe("all", key="X", indexes=["sp500", "nasdaq", "dow", "russell2000"])
    tags = dict((r[0], set(r[3].split())) for r in u)
    ok("union includes NYSE S&P member JPM", "JPM" in tags and tags["JPM"] == {"S", "D"})
    ok("AAPL accumulates S+ND+D", tags.get("AAPL") == {"S", "ND", "D"})
    ok("Nasdaq-only TSLA tagged ND", tags.get("TSLA") == {"ND"})
    ok("Russell SMLL/TINY tagged R", tags.get("SMLL") == {"R"} and tags.get("TINY") == {"R"})
    ok("Exxon (S&P/NYSE) present", "XOM" in tags)
    ok("all four indices represented", all(any(t in s for s in tags.values()) for t in ("S", "ND", "D", "R")))
    u2 = U.fetch_universe("all", key="X", indexes=["sp500", "nasdaq", "dow", "russell2000"], limit=4)
    t2 = dict((r[0], set(r[3].split())) for r in u2)
    ok("limit keeps all S&P+Dow members", all(s in t2 for s in ("JPM", "XOM", "CAT")))
finally:
    U.fetch_constituent, U.fetch_screener_rows, U.fetch_iwm_holdings, U.fetch_nasdaqtrader = _orig
    os.environ.pop("UNIVERSE_MIN", None)

# --- COLLAPSE GUARD: a Dow-only union (index sources down) substitutes the committed seed (floor=60 default) ---
_seed_rows = [("AAA", "Alpha", "Technology", "S"), ("BBB", "Beta", "Energy", "S"),
              ("CCC", "Gamma", "Financials", "S"), ("DDD", "Delta", "Health Care", "S"),
              ("EEE", "Eps", "Industrials", "S"), ("FFF", "Phi", "Utilities", "S")]
_orig2 = (U.fetch_constituent, U.fetch_screener_rows, U.fetch_iwm_holdings, U.fetch_nasdaqtrader, U.load_seed)
U.fetch_constituent = lambda s, k, b, se, v3, tag: ([("AAPL", "Apple", "Unknown", "D")] if tag == "D" else [])
U.fetch_screener_rows = lambda *a, **k: []
U.fetch_iwm_holdings = lambda *a, **k: []
U.fetch_nasdaqtrader = lambda *a, **k: []
U.load_seed = lambda path=None: list(_seed_rows)
try:
    u3 = U.fetch_universe("all", key="X", indexes=["sp500", "nasdaq", "dow", "russell2000"])
    s3 = set(r[0] for r in u3)
    ok("collapse -> seed substituted (size)", len(u3) >= len(_seed_rows))
    ok("collapse -> seed names present", {"AAA", "FFF"} <= s3)
    ok("collapse -> real Dow name preserved", "AAPL" in s3)
    # a HEALTHY union (>= floor) must NOT be replaced by the seed (use valid alpha tickers)
    big = [{"symbol": "TS" + chr(65 + i // 26) + chr(65 + i % 26), "companyName": "C%d" % i,
            "sector": "Technology", "exchangeShortName": "NASDAQ"} for i in range(80)]
    U.fetch_screener_rows = lambda *a, **k: big
    u4 = U.fetch_universe("all", key="X", indexes=["nasdaq"])
    ok("healthy union NOT seed-replaced", u4 is not None and len(u4) >= 80 and "AAA" not in set(r[0] for r in u4))
finally:
    U.fetch_constituent, U.fetch_screener_rows, U.fetch_iwm_holdings, U.fetch_nasdaqtrader, U.load_seed = _orig2

# --- committed seed file loads in the expected shape ---
_sd = U.load_seed("../../data/universe_seed.json")
ok("committed seed loads (>=80 equities)", len(_sd) >= 80)
ok("seed rows are 4-tuples w/ GICS sector", all(len(r) == 4 for r in _sd[:5]) and _sd[0][2] != "Unknown")

# --- mode gating ---
ok("mode seed -> None", U.fetch_universe("seed", key=None) is None)

print("\n" + ("ALL UNIVERSE-FETCH TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
