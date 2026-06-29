#!/usr/bin/env python3
"""Tests for fmp_news parse + fetch (injected fetcher, no network). Run: python3 test_fmp_news.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fmp_news as FN
F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

rows = [
    {"symbol": "AAPL", "publishedDate": "2026-06-28 14:00:00", "title": "Apple beats estimates", "text": "Strong iPhone demand.", "site": "Reuters", "url": "http://x/1"},
    {"symbol": "AAPL", "publishedDate": "2026-06-27", "title": "Apple beats estimates", "text": "dup", "url": "http://x/1"},  # dup title
    {"ticker": "MSFT", "date": "2026-06-28", "headline": "Microsoft faces antitrust probe", "content": "EU opens case."},
    {"symbol": "", "title": "no symbol"},        # dropped
    {"symbol": "TSLA", "title": ""},               # dropped (no title)
]
p = FN.parse_news(rows)
ok("AAPL parsed + deduped", len(p.get("AAPL", [])) == 1, p.get("AAPL"))
ok("MSFT field-variants parsed", p.get("MSFT", [{}])[0]["title"].startswith("Microsoft"), p.get("MSFT"))
ok("empty symbol/title dropped", "TSLA" not in p and len([k for k in p]) == 2, list(p))
ok("normalized fields", set(p["AAPL"][0].keys()) == {"symbol","date","title","summary","site","url"})
ok("want-filter restricts", set(FN.parse_news(rows, want={"AAPL"}).keys()) == {"AAPL"})

# fetch with an injected getter (simulates FMP returning the same rows for both endpoints)
def fake_get(url, timeout=30):
    return 200, rows
got = FN.fetch(["AAPL", "MSFT"], key="X", get=fake_get, per_symbol_limit=5)
ok("fetch merges + dedups across endpoints", len(got.get("AAPL", [])) == 1 and "MSFT" in got, {k: len(v) for k, v in got.items()})
ok("fetch no key -> empty", FN.fetch(["AAPL"], key="", get=fake_get) == {})

# end-to-end: news -> sentiment
import news_sentiment as NS
sent = NS.score_headlines(got.get("AAPL", []), asof="2026-06-28")
ok("AAPL news reads as tailwind", sent["net"] > 0.15, sent)

print("\n" + ("ALL FMP-NEWS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
