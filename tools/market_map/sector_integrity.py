#!/usr/bin/env python3
"""sector_integrity.py — ONE canonical definition of the "sector-rotation is healthy" invariants,
shared by every gate (publish_guards, validate_payload, qa_signoff) so they can never drift apart.

This encodes the exact failure class that shipped silently on 2026-06-28: the universe collapsed to the
Dow-30, every equity's sector became "Unknown", and sectorCorr went empty -> the Sector x factor grid drew
no rows. Any one of these is now a publishable-blocking defect, checked independently at three producer
gates plus a live monitor.

Pure stdlib; offline-tested. Research only."""

GICS = {"Technology", "Financials", "Health Care", "Consumer Disc.", "Communication",
        "Industrials", "Consumer Staples", "Energy", "Utilities", "Materials", "Real Estate"}
SECTORED_FLOOR = 8       # fewer real-sector equities than this => the sector grid is effectively empty
REGRESSION_FRAC = 0.70   # block if names drop below this fraction of the last published build


def sectored_equities(names):
    """Count names carrying a real GICS sector (ETF/macro buckets like 'Commodity' are excluded)."""
    return sum(1 for n in (names or []) if isinstance(n, dict) and n.get("sec") in GICS)


def sectorcorr_empty(payload):
    """True if the sector-correlation matrix is missing or has no rows (grid would not render)."""
    sc = (payload or {}).get("sectorCorr")
    if not isinstance(sc, dict):
        return True
    return len(sc.get("order") or []) == 0 or len(sc.get("m") or []) == 0


def sector_violations(payload, floor=SECTORED_FLOOR, min_universe=80):
    """Return a list of human-readable CORE violations about sector health (empty list = healthy).

    Skips small structural/golden fixtures (universe < min_universe): sector-collapse is only
    meaningful for a full build, and thin-universe is a separate gate, so a tiny payload is never
    double-penalized."""
    out = []
    names = (payload or {}).get("names") or []
    if len(names) < min_universe:
        return out
    sectored = sectored_equities(names)
    if sectored < floor:
        out.append("sector collapse: only %d GICS-sectored equities (<%d) — every equity 'Unknown'? "
                   "the Sector x factor grid would be empty" % (sectored, floor))
    elif sectorcorr_empty(payload):
        out.append("sectorCorr empty while %d sectored equities exist — the correlation grid would not render"
                   % sectored)
    return out


def regression_violation(names, prev_names, frac=REGRESSION_FRAC):
    """One violation string if the universe collapsed vs the last published build, else None."""
    n, p = len(names or []), len(prev_names or [])
    if p >= 80 and n < frac * p:
        return ("universe regression: %d names vs %d previously published (<%d%% — likely a collapsed fetch)"
                % (n, p, int(frac * 100)))
    return None


def summary(payload):
    """Compact health summary for logs/artifacts."""
    names = (payload or {}).get("names") or []
    return {"names": len(names), "sectoredEquities": sectored_equities(names),
            "sectorCorrEmpty": sectorcorr_empty(payload), "asof": (payload or {}).get("asof")}
