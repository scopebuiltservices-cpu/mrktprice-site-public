"""Publish-time integrity + health guards for the Market Map snapshot (GATE 1 of 3).

Philosophy (from the mastery audit): make failure loud, but distinguish CORE-data failures (which must
BLOCK publishing) from ENRICHMENT-layer degradation (surfaced loudly but never blocking). A missing FMP
valuation layer should not stop prices/charts/macro from updating; a SAMPLE fallback, a truncated/stale
core file, OR a sector/universe collapse must.

The sector/universe-collapse invariants are the shared canonical ones in sector_integrity.py, also enforced
independently at validate_payload.py (contract gate) and qa_signoff.py (release gate) — defense in depth.

Exit 0 = safe to publish (enrichment warnings may have been emitted).
Exit 1 = CORE data is broken; caller must NOT publish.

Usage: python publish_guards.py path/to/marketmap.json [--prev path/to/previous.json]
       (if --prev is omitted, the committed ./marketmap.json is used as the baseline when distinct)
"""
import json
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sector_integrity as SI


def load_or_die(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _try_load(path):
    try:
        return load_or_die(path)
    except Exception:
        return None


def evaluate(d, prev=None):
    """Return (core_errs, warnings, stats). Pure -> unit-testable without files/exit."""
    names = d.get("names", []) or []
    src = str(d.get("source", ""))
    core_errs = []

    # --- CORE gate: fundamental dataset unusable ---
    if "SAMPLE" in src or "synthetic" in src.lower():
        core_errs.append("source is SAMPLE/synthetic (real build fell back)")
    if len(names) < 80:
        core_errs.append("thin universe: only %d names (expected >=80)" % len(names))
    try:
        asof = dt.date.fromisoformat(str(d.get("asof")))
        age = (dt.date.today() - asof).days
        if age > 3:
            core_errs.append("stale asof %s (%d days old)" % (d.get("asof"), age))
    except Exception as e:
        core_errs.append("unparseable asof %r: %s" % (d.get("asof"), e))

    # --- CORE gate: silent-regression invariants (the 2026-06-28 failure class) ---
    core_errs += SI.sector_violations(d)
    if prev is not None:
        rv = SI.regression_violation(names, prev.get("names", []) or [])
        if rv:
            core_errs.append(rv)

    # --- ENRICHMENT health: loud warnings, never block ---
    warnings = []
    dh = d.get("dataHealth", {}) or {}
    if dh.get("fmpTried", 0) and not dh.get("fmpOk", 0):
        warnings.append("FMP valuations 0/%s (keyValid=%s reason=%s) — valuation cross-check degraded; publishing core data"
                        % (dh.get("fmpTried"), dh.get("fmpKeyValid"), dh.get("fmpKeyReason")))
    if dh.get("eodTried", 0) and not dh.get("eodOk", 0):
        warnings.append("EODHD options 0/%s — dealer-gamma layer degraded" % dh.get("eodTried"))

    nv = sum(1 for n in names if n.get("val") and any(n["val"].get(k) is not None for k in ("pe", "fpe", "peg", "evb")))
    cov = round(100.0 * nv / max(1, len(names)), 1)
    if cov == 0.0:
        warnings.append("valuation coverage 0%% across %d names — check FMP/yfinance valuation source" % len(names))

    stats = SI.summary(d); stats["valuationCoveragePct"] = cov; stats["source"] = src[:48]
    return core_errs, warnings, stats


def main(path="marketmap.json", prev_path=None):
    try:
        d = load_or_die(path)
    except Exception as e:
        sys.stderr.write("::error::publish blocked: %s is not valid JSON (truncated/corrupt?): %s\n" % (path, e))
        return 1

    prev = None
    if prev_path:
        prev = _try_load(prev_path)
    elif os.path.abspath(path) != os.path.abspath("marketmap.json") and os.path.exists("marketmap.json"):
        prev = _try_load("marketmap.json")

    core_errs, warnings, stats = evaluate(d, prev=prev)
    if core_errs:
        for e in core_errs:
            sys.stderr.write("::error::publish blocked: %s\n" % e)
        return 1
    for w in warnings:
        sys.stderr.write("::warning::%s\n" % w)

    sys.stderr.write("publish guards PASS (core ok): names=%d sectoredEquities=%d valuation_coverage=%s%% source=%s\n"
                     % (stats["names"], stats["sectoredEquities"], stats["valuationCoveragePct"], str(stats["source"])[:36]))
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    p = "marketmap.json"; prev = None; i = 0
    while i < len(args):
        if args[i] == "--prev" and i + 1 < len(args):
            prev = args[i + 1]; i += 2
        else:
            p = args[i]; i += 1
    sys.exit(main(p, prev))
