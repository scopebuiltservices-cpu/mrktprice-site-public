"""pit_engine.py — point-in-time (PIT) leakage control. The #1 safety item: never let a feature whose
information was not yet PUBLIC at the decision time enter a backtest or live decision. Pure stdlib; verified.

Core guard:  a feature row carries available_at (when it became public). At a decision made at decision_ts,
DROP any feature with available_at > decision_ts. SEC fundamentals only become available at their FILING
date (not the fiscal period end), with statutory deadlines:
   10-K: 60 / 75 / 90 days after FY end (large-accelerated / accelerated / non-accelerated)
   10-Q: 40 / 40 / 45 days after quarter end
EDGAR accepts filings weekdays 06:00-22:00 ET; a filing accepted after 22:00 (or on a weekend) is treated
as available the next business day.

Functions:
  filing_deadline(period_end, form, filer)         -> latest legal availability date (conservative bound)
  available_at(filing_date, accepted_iso)          -> the effective public timestamp (next-biz-day rule)
  leak_guard(features, decision_ts)                -> features with available_at <= decision_ts only
  replay_ok(decisions)                             -> True iff every decision used only data available then
"""
import datetime as dt

__all__ = ["filing_deadline", "available_at", "leak_guard", "replay_ok", "FILING_LAG"]

# days after period end by (form, filer-tier)
FILING_LAG = {
    ("10-K", "large"): 60, ("10-K", "accel"): 75, ("10-K", "non"): 90,
    ("10-Q", "large"): 40, ("10-Q", "accel"): 40, ("10-Q", "non"): 45,
}


def _d(x):
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


def filing_deadline(period_end, form="10-K", filer="large"):
    """Conservative latest date the filing's data could be public (period_end + statutory lag)."""
    lag = FILING_LAG.get((form, filer), 90)
    return _d(period_end) + dt.timedelta(days=lag)


def _next_business_day(d):
    d = d + dt.timedelta(days=1)
    while d.weekday() >= 5:   # Sat/Sun
        d = d + dt.timedelta(days=1)
    return d


def available_at(filing_date, accepted_iso=None):
    """Effective public date. If the EDGAR acceptance timestamp is after 22:00 ET or on a weekend, the data
    is treated as available the NEXT business day (a conservative no-leak bound)."""
    fd = _d(filing_date)
    if accepted_iso:
        try:
            ts = dt.datetime.fromisoformat(str(accepted_iso).replace("Z", "+00:00"))
            # ET ~ UTC-5/-4; use a conservative 22:00 ET ≈ 02:00-03:00 UTC next day. Treat hour>=22 local-naive
            hod = ts.hour
            if ts.weekday() >= 5 or hod >= 22:
                return _next_business_day(fd)
        except Exception:
            pass
    if fd.weekday() >= 5:
        return _next_business_day(fd - dt.timedelta(days=1))
    return fd


def leak_guard(features, decision_ts):
    """features: list of dicts each with 'available_at' (date/iso). Returns only those public by decision_ts.
    A feature missing available_at is DROPPED (fail-closed: unknown provenance = potential leak)."""
    dts = _d(decision_ts)
    out = []
    for f in features:
        av = f.get("available_at")
        if av is None:
            continue
        try:
            if _d(av) <= dts:
                out.append(f)
        except Exception:
            continue
    return out


def replay_ok(decisions):
    """decisions: list of {decision_ts, features:[{available_at,...}]}. True iff NO decision used a feature
    that wasn't yet available — i.e. leak_guard is a no-op for every decision."""
    for dec in decisions:
        kept = leak_guard(dec.get("features", []), dec["decision_ts"])
        if len(kept) != len([f for f in dec.get("features", []) if f.get("available_at") is not None]):
            return False
        # any feature with available_at strictly after the decision is a leak
        dts = _d(dec["decision_ts"])
        for f in dec.get("features", []):
            av = f.get("available_at")
            if av is not None and _d(av) > dts:
                return False
    return True
