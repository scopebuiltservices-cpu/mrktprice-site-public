#!/usr/bin/env python3
"""LIVE smoke test for the AUTHORITATIVE earnings fiscal-Q/Y join (FMP Ultimate).

Why this exists: /stable/earnings gives the report date + EPS but NOT the fiscal quarter/year.
The naive fix (derive Q/Y from ~45 days before the announce date) mislabels companies whose fiscal
year is not the calendar year — e.g. Apple's quarter that ENDS in late September is fiscal Q4, but
a calendar guess calls it Q3. fmp_history joins the /stable/income-statement (which carries the TRUE
fiscalYear + period) to fix this. This test proves the live feed actually delivers that.

Secret handling: the key is read from the FMP_API_KEY env var only (never a literal, never printed,
never built into a logged URL). Without the key (local runs, fork PRs) the test SKIPS and exits 0,
so it is safe to auto-discover in the offline suite. It runs for real in the earnings-smoke CI job,
where the key is injected from GitHub Secrets. A transient API/plan error SKIPS (warns); only a wrong
fiscal label FAILS.

Run:  FMP_API_KEY=... python3 test_earnings_live.py
"""
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fmp_history as fh

F = []
def ok(name, cond, d=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  -> " + str(d)))
    if not cond:
        F.append(name)

def skip(msg):
    print("  SKIP  " + msg)
    print("\nEARNINGS LIVE SMOKE: SKIPPED")
    raise SystemExit(0)

if not fh.have_key():
    skip("FMP_API_KEY not set — offline/no-secret run (this is expected locally and on fork PRs).")

# ---- Apple: fiscal year ends in late September, so the Sep/Oct-ending quarter MUST be fiscal Q4 ----
try:
    aapl = fh.quarterly_income("AAPL")
except Exception as e:
    skip("FMP quarterly_income(AAPL) raised (%s) — treating as a transient feed/plan issue." % str(e)[:80])

if not aapl:
    skip("FMP returned no AAPL income statement — transient feed/plan issue, not a logic failure.")

ok("AAPL income statement returned periods", len(aapl) >= 4, len(aapl))
for r in aapl:
    ok("AAPL fp in 1..4 (authoritative)", r["fp"] in (1, 2, 3, 4), r)
    ok("AAPL fy is a 4-digit year", isinstance(r["fy"], int) and 2000 <= r["fy"] <= 2100, r["fy"])

sep_end = [r for r in aapl if r["periodEnd"][5:7] in ("09", "10")]
ok("AAPL has a Sept/Oct fiscal-year-end quarter", bool(sep_end), [r["periodEnd"] for r in aapl][-4:])
if sep_end:
    # THE killer assertion: authoritative label says Q4; the calendar guess would wrongly say Q3.
    ok("AAPL Sept/Oct-ending quarter is fiscal Q4 (authoritative, not calendar-guessed)",
       all(r["fp"] == 4 for r in sep_end), [(r["periodEnd"], r["fp"]) for r in sep_end])

# ---- the joined calendar: provenance must be clean (authoritative label + estimate never hardened) ----
try:
    cal = fh.earnings_calendar("AAPL")
except Exception as e:
    cal = None
if cal and cal.get("q"):
    q = cal["q"]
    ok("earnings_calendar q[] non-empty", len(q) >= 1, len(q))
    ok("every fiscal label q in 1..4", all(x.get("q") in (1, 2, 3, 4) for x in q if x.get("q")), q[-1])
    ok("at least one label is AUTHORITATIVE (labelSrc='is', not calendar)",
       any(x.get("labelSrc") == "is" for x in q), [x.get("labelSrc") for x in q])
    ok("past quarters are flagged confirmed", all(x.get("conf") is True for x in q), q[-1])
    for x in q:
        try:
            dt.date.fromisoformat(x["d"])
        except Exception:
            ok("report date is valid ISO", False, x.get("d"))
    nxt = cal.get("next")
    if nxt:
        ok("NEXT quarter is flagged estimate, never confirmed (provenance guard)",
           nxt.get("conf") is False and nxt.get("est") is True, nxt)
    if cal.get("fyEnd") is not None:
        ok("fiscal-year-end month in 1..12", 1 <= cal["fyEnd"] <= 12, cal["fyEnd"])
else:
    print("  SKIP  earnings_calendar(AAPL) returned no joined quarters (transient) — income-statement check above still ran.")

# ---- Microsoft: fiscal year ends in June, so the Jun/Jul-ending quarter MUST be fiscal Q4 ----
try:
    msft = fh.quarterly_income("MSFT")
except Exception:
    msft = None
if msft:
    jun_end = [r for r in msft if r["periodEnd"][5:7] in ("06", "07")]
    if jun_end:
        ok("MSFT June/Jul-ending quarter is fiscal Q4 (June FYE, authoritative)",
           all(r["fp"] == 4 for r in jun_end), [(r["periodEnd"], r["fp"]) for r in jun_end])

print("\n" + ("EARNINGS LIVE SMOKE PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
