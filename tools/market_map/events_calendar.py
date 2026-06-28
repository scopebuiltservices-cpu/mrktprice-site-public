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
import os, json, datetime

STABLE = "https://financialmodelingprep.com/stable"
# event-name patterns that move the whole tape (case-insensitive), beyond FMP's own "High" impact tag
KEY_PATTERNS = ("fomc", "federal funds", "fed interest rate", "interest rate decision", "cpi",
                "consumer price", "pce", "core pce", "nonfarm", "non-farm", "payroll", "unemployment rate",
                "gdp", "ism manufacturing", "ism services", "retail sales", "ppi", "producer price",
                "fed chair", "powell", "jackson hole")


def _key():
    for k in ("FMP_API_KEY", "FMP_ULTIMATE_API_KEY", "FMP_UTIMATE_API_KEY"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


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


def normalize(ev):
    return {"date": str(ev.get("date") or "")[:10], "event": ev.get("event"),
            "impact": ev.get("impact"), "actual": ev.get("actual"),
            "estimate": ev.get("estimate"), "previous": ev.get("previous")}


def build_events(raw, today=None):
    """From a raw FMP economic-calendar list -> {asof, nextHighImpact, daysToNext, upcoming[], recent[]}."""
    today = today or datetime.date.today()
    hi = [normalize(e) for e in (raw or []) if is_high_impact(e)]
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
