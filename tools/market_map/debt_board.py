#!/usr/bin/env python3
"""debt_board.py — POST-BUILD enrichment: land per-name DEBT / leverage into marketmap.json.

Same external-enrichment pattern as event_board.py / crowding_board.py: reads the committed
marketmap.json + cik.json (ticker->CIK), pulls each issuer's multi-year balance-sheet + income
items from SEC XBRL company-facts (keyless, via sec_debt), computes leverage/credit metrics + a
bounded credit tilt (via debt_engine), and writes:

    n["debt"] = {netDebt, ev, evEbitda, netDebtEbitda, debtEquity, coverage, netCash,
                 growth:{pct,last,cagr,levels}, tilt, verdict, asOf, src}

The board nets `debt.tilt` into the displayed alpha (client-side, like event.tilt); the tilt is
bounded to [-1,1] so a single noisy filing can't dominate the rank. Equity-only (ETFs/factors are
skipped — no issuer facts). Idempotent, defensive, verified in test_debt_board.py. Research only.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sec_debt
import debt_engine

_MCAP_KEYS = ("mcap", "cap", "marketCap", "mktcap", "marketcap")


def _mcap(node):
    for k in _MCAP_KEYS:
        v = node.get(k)
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def debt_for(node, cf):
    """Pure enrichment: node + already-fetched companyfacts -> the n['debt'] block, or None if there
    is no debt/balance-sheet signal to score. Network-free so it is unit-testable."""
    snap = sec_debt.debt_snapshot(cf or {})
    if snap["totalDebt"] is None and not snap["debtSeries"]:
        return None
    rep = debt_engine.debt_report(
        mktcap=_mcap(node),
        total_debt=snap["totalDebt"],
        cash=snap["cashAndSti"] if snap["cashAndSti"] is not None else snap["cash"],
        equity=snap["equity"], ebitda=snap["ebitda"], ebit=snap["ebit"],
        interest_expense=snap["interestExpense"], debt_series=snap["debtSeries"],
    )
    rep["asOf"] = snap["debtDates"][-1] if snap["debtDates"] else None
    rep["src"] = "SEC XBRL companyfacts (10-K)"
    return rep


def _is_equity(node):
    idx = node.get("idx") or []
    t = (node.get("t") or "").upper()
    return bool(t) and "FACTOR" not in idx and not node.get("etf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--cik", required=True, help="cik.json: {ticker: cik|{cik:...}}")
    ap.add_argument("--limit", type=int, default=0, help="cap number of network pulls (0 = all)")
    a = ap.parse_args()

    mm = json.load(open(a.map))
    names = mm.get("names") or mm.get("nodes") or []
    ciks = json.load(open(a.cik)) if os.path.exists(a.cik) else {}

    def _cik_of(t):
        v = ciks.get(t) or ciks.get(t.upper())
        if isinstance(v, dict):
            v = v.get("cik") or v.get("cik_str")
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    try:
        import requests
        sess = requests.Session(); sess.headers.update(sec_debt.UA)
    except Exception:
        sess = None

    done = 0
    for n in names:
        if not _is_equity(n):
            continue
        cik = _cik_of(n.get("t", ""))
        if cik is None:
            continue
        cf = sec_debt.fetch_companyfacts(cik, session=sess)
        if not cf:
            continue
        block = debt_for(n, cf)
        if block:
            n["debt"] = block; done += 1
        if a.limit and done >= a.limit:
            break

    tmp = a.map + ".tmp"
    json.dump(mm, open(tmp, "w"))
    os.replace(tmp, a.map)
    sys.stderr.write("debt_board: enriched %d names with SEC leverage -> %s\n" % (done, a.map))


if __name__ == "__main__":
    main()
