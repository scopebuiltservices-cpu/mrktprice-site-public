#!/usr/bin/env python3
"""
trial_ledger.py — HONEST multiple-testing trial ledger (stdlib).

The deflated Sharpe ratio (Bailey & Lopez de Prado) only has teeth when the multiple-testing count
is honest. Per the deep-research spec, that count must include every configuration actually evaluated:
factor subsets, lookback variants, holding horizons, threshold grids, rebalancing rules, and any
alternative post-processing paths that were tried and rejected. This module keeps a persistent,
append-only ledger of those trials so the composite DSR gate can be fed a real number instead of "1".

Storage: a JSONL file, one record per logged batch of trials:
    {"asof": "2026-06-27", "category": "thresholdGrid", "n": 80, "note": "RVOL cutoff grid"}

The total trial count is the SUM of n across all records (deduped is intentionally NOT done — every
genuine evaluation counts). A small set of standing categories is recognized for reporting.
"""
import json, os, datetime

CATEGORIES = ("factorSubset", "lookback", "horizon", "thresholdGrid", "rebalanceRule", "postProcess", "other")


def record(path, category, n, note="", asof=None):
    """Append a trial batch. n = number of configurations evaluated in this batch (>=0)."""
    n = int(max(0, n))
    cat = category if category in CATEGORIES else "other"
    rec = {"asof": asof or datetime.date.today().isoformat(), "category": cat, "n": n, "note": str(note)[:120]}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def read_all(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def totals(path, extra=0):
    """Total honest trial count = sum of all logged n + any `extra` counted live this run (e.g. the
    current threshold grid size). Returns {total, byCategory:{...}, records}. Floor of 1 so DSR is defined."""
    recs = read_all(path)
    by = {c: 0 for c in CATEGORIES}
    tot = 0
    for r in recs:
        c = r.get("category", "other"); n = int(r.get("n", 0) or 0)
        by[c] = by.get(c, 0) + n; tot += n
    tot += int(max(0, extra))
    return {"total": max(1, tot), "byCategory": by, "records": len(recs), "liveExtra": int(max(0, extra))}
