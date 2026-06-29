#!/usr/bin/env python3
"""Tests for news_sentiment (pure). Run: python3 test_news_sentiment.py"""
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import news_sentiment as NS
F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

ok("clearly positive headline", NS.score_text("Company beats estimates, raises guidance, shares surge")["polarity"] > 0.5)
ok("clearly negative headline", NS.score_text("Firm misses earnings, cuts guidance, faces lawsuit and layoffs")["polarity"] < -0.5)
ok("negation flips positive", NS.score_text("revenue did not grow")["polarity"] <= 0)
ok("neutral headline ~0", abs(NS.score_text("The company will host its annual meeting on Tuesday")["polarity"]) < 0.2)

TODAY = dt.date.today().isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()
heads = [
    {"title": "Acme beats and raises, stock surges to record", "date": TODAY},
    {"title": "Acme wins major partnership, analysts upgrade", "date": YESTERDAY},
    {"title": "Acme faces minor recall concern", "date": (dt.date.today()-dt.timedelta(days=20)).isoformat()},
]
agg = NS.score_headlines(heads, asof=TODAY)
ok("net positive tailwind", agg["net"] > 0.15 and agg["label"] == "tailwind", agg)
ok("recency: old negative is decayed", agg["headwind"] < agg["tailwind"], agg)
ok("drivers surfaced", len(agg["topPos"]) >= 1)

bad = NS.score_headlines([{"title": "Beta plunges on fraud probe, downgrade, bankruptcy fears", "date": TODAY}], asof=TODAY)
ok("headwind label", bad["label"] == "headwind", bad)

empty = NS.score_headlines([], asof=TODAY)
ok("no news -> neutral", empty["label"] == "no-news" and empty["net"] == 0.0)

roll = NS.aggregate({"A": {"net": 0.4, "n": 3}, "B": {"net": -0.1, "n": 2}}, weights={"A": 3.0, "B": 1.0})
ok("cap-weighted rollup leans to A", roll["net"] > 0.2 and roll["label"] == "tailwind", roll)

print("\n" + ("ALL NEWS-SENTIMENT TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
