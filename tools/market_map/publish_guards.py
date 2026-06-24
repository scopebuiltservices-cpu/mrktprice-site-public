"""Publish-time integrity + health guards for the Market Map snapshot.

Philosophy (from the mastery audit): make failure loud, but distinguish
CORE-data failures (which must BLOCK publishing) from ENRICHMENT-layer
degradation (which must be surfaced loudly but should NOT take the whole
site down). A missing FMP valuation layer should not stop prices/charts/
macro from updating; a SAMPLE fallback or a truncated/stale core file must.

Exit 0 = safe to publish (enrichment warnings may have been emitted).
Exit 1 = CORE data is broken; caller must NOT publish.

Usage: python publish_guards.py path/to/marketmap.json
"""
import json
import sys
import datetime as dt


def load_or_die(path):
    # json.load raises on truncated/corrupt files -> caught below as a CORE failure.
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(path="marketmap.json"):
    try:
        d = load_or_die(path)
    except Exception as e:
        sys.stderr.write("::error::publish blocked: %s is not valid JSON (truncated/corrupt?): %s\n" % (path, e))
        return 1

    names = d.get("names", []) or []
    src = str(d.get("source", ""))
    core_errs = []

    # --- CORE gate: these mean the fundamental dataset is unusable ---
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

    if core_errs:
        for e in core_errs:
            sys.stderr.write("::error::publish blocked: %s\n" % e)
        return 1

    # --- ENRICHMENT health: loud warnings, never block ---
    dh = d.get("dataHealth", {}) or {}
    if dh.get("fmpTried", 0) and not dh.get("fmpOk", 0):
        sys.stderr.write(
            "::warning::FMP valuations 0/%s (keyValid=%s reason=%s) — valuation cross-check degraded; publishing core data\n"
            % (dh.get("fmpTried"), dh.get("fmpKeyValid"), dh.get("fmpKeyReason"))
        )
    if dh.get("eodTried", 0) and not dh.get("eodOk", 0):
        sys.stderr.write("::warning::EODHD options 0/%s — dealer-gamma layer degraded\n" % dh.get("eodTried"))

    nv = sum(
        1
        for n in names
        if n.get("val") and any(n["val"].get(k) is not None for k in ("pe", "fpe", "peg", "evb"))
    )
    cov = round(100.0 * nv / max(1, len(names)), 1)
    if cov == 0.0:
        sys.stderr.write("::warning::valuation coverage 0%% across %d names — check FMP/yfinance valuation source\n" % len(names))

    sys.stderr.write(
        "publish guards PASS (core ok): names=%d valuation_coverage=%s%% source=%s\n" % (len(names), cov, src[:36])
    )
    print(json.dumps({"names": len(names), "valuationCoveragePct": cov, "asof": d.get("asof")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "marketmap.json"))
