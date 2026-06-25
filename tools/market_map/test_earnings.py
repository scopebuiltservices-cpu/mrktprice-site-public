#!/usr/bin/env python3
"""Unit test for the AUTHORITATIVE earnings/fiscal join in fmp_history.earnings_calendar.

No network: monkeypatches _get to serve synthetic FMP income-statement + earnings-calendar payloads
for an Apple-like SEPTEMBER fiscal year — the exact case the old "announce date - 45 days" heuristic
mislabels. Asserts the merged result carries the TRUE fiscal Q/Y (from the income statement), the real
filing dates, the surprise vs the matched estimate, the rolled-forward next label, and the company
fiscal cadence (fyEnd / qMonths). Run: python3 test_earnings.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fmp_history as fh

INC = [
    {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "filingDate": "2025-08-01", "epsDiluted": 1.40},
    {"date": "2025-09-27", "period": "Q4", "fiscalYear": 2025, "filingDate": "2025-10-30", "epsDiluted": 1.65},
    {"date": "2025-12-27", "period": "Q1", "fiscalYear": 2026, "filingDate": "2026-01-30", "epsDiluted": 2.40},
    {"date": "2026-03-28", "period": "Q2", "fiscalYear": 2026, "filingDate": "2026-05-01", "epsDiluted": 1.55},
]
CAL = [
    {"date": "2025-08-01", "epsActual": 1.40, "epsEstimated": 1.34},
    {"date": "2025-10-30", "epsActual": 1.65, "epsEstimated": 1.60},
    {"date": "2026-01-30", "epsActual": 2.40, "epsEstimated": 2.35},
    {"date": "2026-05-01", "epsActual": 1.55, "epsEstimated": 1.58},
    {"date": "2026-08-06", "epsActual": None, "epsEstimated": 1.45},
]


class _R:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def main():
    fh._key = lambda: "TESTKEY"
    fh._get = lambda s, url, timeout=25, tries=3: _R(INC if "income-statement" in url else CAL)

    out = fh.earnings_calendar("AAPL")
    fails = []

    def ok(name, cond):
        print(("  PASS  " if cond else "  FAIL  ") + name)
        if not cond:
            fails.append(name)

    ok("returns a result", out is not None)
    labels = [(q["q"], q["y"]) for q in out["q"]]
    ok("authoritative fiscal labels Q3'25..Q2'26 (not -45d guess)",
       labels == [(3, 2025), (4, 2025), (1, 2026), (2, 2026)])
    ok("all past quarters sourced from income statement", all(q["src"] == "is" for q in out["q"]))
    ok("report dates are the real filing dates", out["q"][0]["d"] == "2025-08-01" and out["q"][2]["d"] == "2026-01-30")
    ok("surprise computed from matched estimate (Q2 miss < 0)", out["q"][-1]["s"] is not None and out["q"][-1]["s"] < 0)
    ok("next quarter rolled forward to Q3 FY2026", out.get("next") and out["next"]["q"] == 3 and out["next"]["y"] == 2026)
    ok("next carries the estimate, no actual", out["next"]["e"] == 1.45 and out["next"]["a"] is None)
    ok("fiscal-year-end month = September (9)", out.get("fyEnd") == 9)
    ok("report-month cadence captured", out.get("qMonths") == [1, 5, 8, 10])
    ok("Bayesian-shrunk beat rate in (0,1)", 0 < out.get("beat", -1) < 1)

    # PROVENANCE CONTRACT — a cadence guess must never sit unflagged beside confirmed dates
    ok("past quarters flagged confirmed", all(q.get("conf") is True for q in out["q"]))
    ok("past labels carry a source tag (is/sec/cal)", all(q.get("labelSrc") in ("is", "sec", "cal") for q in out["q"]))
    ok("past labels here are authoritative (income statement)", all(q.get("labelSrc") == "is" for q in out["q"]))
    nx = out["next"]
    ok("NEXT explicitly NOT confirmed", nx.get("conf") is False)
    ok("NEXT flagged as an estimate", nx.get("est") is True and nx.get("labelEst") is True)
    ok("NEXT carries an estimate status", nx.get("status") in ("scheduled", "estimated"))
    ok("NEXT never hardens to a point (has a window)", isinstance(nx.get("window"), list) and len(nx["window"]) == 2)
    ok("NEXT window brackets the date", nx["window"][0] <= nx["d"] <= nx["window"][1])

    # the smoking gun: the old heuristic on the Jan filing would mislabel the fiscal quarter
    import datetime as dt
    pe = dt.date(2026, 1, 30) - dt.timedelta(days=45)
    old_q = (pe.month - 1) // 3 + 1
    ok("old -45d heuristic WOULD mislabel (Q%d) vs true Q1" % old_q, old_q != 1)

    print("\n" + ("ALL EARNINGS-JOIN TESTS PASSED" if not fails else "%d FAILED: %s" % (len(fails), fails)))
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
