#!/usr/bin/env python3
"""
events_calendar.py — high-impact US macro event calendar from FMP Ultimate (stdlib + requests).

Sources the economic calendar live (FOMC, CPI, PCE, Nonfarm Payrolls, GDP, Unemployment, ISM, Retail
Sales, ...) instead of hard-coding dates, so the event layer is credible and current. Emits events.json
and a compact `events` block for the payload: the next high-impact event + the upcoming window, plus
`daysToNext` so the conviction/drift layers can be EVENT-AWARE (treat a signal cautiously right before a
major print, and expect a distribution shift right after one).

FMP stable endpoint: /stable/economic-calendar?from=&to=&apikey=. Fail-soft: returns None without a key
or on any error, so the build degrades gracefully. Parser is unit-tested against a fixture (no network).
"""
import os, json, datetime, hashlib, re

STABLE = "https://financialmodelingprep.com/stable"
# event-name patterns that move the whole tape (case-insensitive), beyond FMP's own "High" impact tag
KEY_PATTERNS = ("fomc", "federal funds", "fed interest rate", "interest rate decision", "cpi",
                "consumer price", "pce", "core pce", "nonfarm", "non-farm", "payroll", "unemployment rate",
                "gdp", "ism manufacturing", "ism services", "retail sales", "ppi", "producer price",
                "fed chair", "powell", "jackson hole")


def _key():
    v = os.environ.get("FMP_ULTIMATE_API_KEY", "").strip()
    return v if v else ""


def is_high_impact(ev):
    """US/USD event that is either FMP-tagged High impact or matches a market-moving name pattern."""
    country = str(ev.get("country") or "").upper()
    cur = str(ev.get("currency") or "").upper()
    if country not in ("US", "USA", "UNITED STATES") and cur != "USD":
        return False
    impact = str(ev.get("impact") or "").lower()
    name = str(ev.get("event") or "").lower()
    if impact == "high":
        return True
    return any(p in name for p in KEY_PATTERNS)


def _norm_name(name):
    """Lowercase + collapse whitespace/punctuation so the same event canonicalizes identically across runs."""
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def _canonical_id(date, event, source):
    """Stable deterministic id: first 12 hex chars of sha1(date|normalized-name|source).
    Same event from the same source produces the same id, so rows dedupe/align across runs."""
    basis = "%s|%s|%s" % (str(date or "")[:10], _norm_name(event), str(source or "").lower())
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _session_of(ev):
    """Derive the trading session from an event time if present.
    America/New_York wall-clock buckets (US equities): premarket <09:30, regular 09:30-16:00,
    afterhours >=16:00. Returns 'unknown' when no parseable HH:MM time is available."""
    raw = str(ev.get("time") or ev.get("date") or "")
    m = re.search(r"(\d{1,2}):(\d{2})", raw)
    if not m:
        return "unknown"
    mins = int(m.group(1)) * 60 + int(m.group(2))
    if mins < 9 * 60 + 30:
        return "premarket"
    if mins < 16 * 60:
        return "regular"
    return "afterhours"


def _confidence(ev):
    """Completeness rubric in [0,1]:
      1.0 -> actual is present (the print has landed / fully observed)
      0.6 -> only estimate/forecast present (forward-looking, not yet observed)
      0.4 -> only a bare date/event (scheduled, no numbers)."""
    def _has(v):
        return v not in (None, "")
    if _has(ev.get("actual")):
        return 1.0
    if _has(ev.get("estimate")) or _has(ev.get("forecast")):
        return 0.6
    return 0.4


def normalize(ev, source="fmp", source_ts=None, timezone="America/New_York"):
    """Normalize one raw calendar row into the audited per-event contract.

    Adds provenance fields with safe defaults so existing consumers (which only read
    date/event/impact/actual/estimate/previous) keep working unchanged:
      source          - data origin (provider/feed name); 'fmp' by default, 'unknown' if blank.
      sourceTimestamp - ISO8601 ingest/observation time (build/asof time passed by caller); null if absent.
      timezone        - calendar wall-clock zone; 'America/New_York' unless the row overrides via ev['timezone'].
      session         - premarket/regular/afterhours/unknown, derived from event time (see _session_of).
      canonicalId     - sha1(date|normalized-name|source)[:12], stable across runs for dedupe/alignment.
      revision        - integer revision counter; default 0. Bumping on later actual/estimate changes for the
                        same canonicalId needs cross-run bookkeeping that isn't available in this pure pass,
                        so it stays 0 here (a downstream store can increment it).
      confidence      - completeness score in [0,1] (see _confidence)."""
    date = str(ev.get("date") or "")[:10]
    src = (str(source).strip() or "unknown") if source is not None else "unknown"
    return {"date": date, "event": ev.get("event"),
            "impact": ev.get("impact"), "actual": ev.get("actual"),
            "estimate": ev.get("estimate"), "previous": ev.get("previous"),
            "source": src,
            "sourceTimestamp": source_ts,
            "timezone": ev.get("timezone") or timezone,
            "session": _session_of(ev),
            "canonicalId": _canonical_id(date, ev.get("event"), src),
            "revision": int(ev.get("revision") or 0),
            "confidence": _confidence(ev)}


def build_events(raw, today=None, source="fmp", source_ts=None):
    """From a raw FMP economic-calendar list -> {asof, nextHighImpact, daysToNext, upcoming[], recent[]}.

    source/source_ts flow into each event's provenance fields. source_ts defaults to the build/asof
    instant (today at midnight, ISO8601) when the caller does not supply one."""
    today = today or datetime.date.today()
    if source_ts is None:
        source_ts = datetime.datetime(today.year, today.month, today.day).isoformat()
    hi = [normalize(e, source=source, source_ts=source_ts) for e in (raw or []) if is_high_impact(e)]
    def _d(s):
        try:
            return datetime.date.fromisoformat(str(s)[:10])
        except Exception:
            return None
    hi = [e for e in hi if _d(e["date"])]
    hi.sort(key=lambda e: e["date"])
    upcoming = [e for e in hi if _d(e["date"]) >= today]
    recent = [e for e in hi if _d(e["date"]) < today][-10:]
    nxt = upcoming[0] if upcoming else None
    days = (_d(nxt["date"]) - today).days if nxt else None
    return {"asof": today.isoformat(), "schemaVersion": "1.0",
            "nextHighImpact": nxt, "daysToNext": days,
            "upcoming": upcoming[:15], "recent": recent}


def fetch_economic_calendar(sess=None, days_back=10, days_fwd=21):
    key = _key()
    if not key:
        return None
    try:
        import requests
    except Exception:
        return None
    today = datetime.date.today()
    frm = (today - datetime.timedelta(days=days_back)).isoformat()
    to = (today + datetime.timedelta(days=days_fwd)).isoformat()
    url = "%s/economic-calendar?from=%s&to=%s&apikey=%s" % (STABLE, frm, to, key)
    try:
        r = (sess or requests).get(url, timeout=30)
        if r.status_code != 200:
            return None
        j = r.json()
        return j if isinstance(j, list) else None
    except Exception:
        return None


def emit(out_path="events.json", sess=None):
    """Fetch + build + write events.json. Returns the events block, or None if unavailable."""
    raw = fetch_economic_calendar(sess)
    if raw is None:
        return None
    ev = build_events(raw)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ev, f, separators=(",", ":"))
    except Exception:
        pass
    return ev


if __name__ == "__main__":
    import sys
    e = emit(sys.argv[1] if len(sys.argv) > 1 else "events.json")
    print("events.json: nextHighImpact=%s daysToNext=%s" % ((e or {}).get("nextHighImpact", {}) and (e or {}).get("nextHighImpact", {}).get("event"), (e or {}).get("daysToNext")) if e else "events unavailable (no key / no data)")
