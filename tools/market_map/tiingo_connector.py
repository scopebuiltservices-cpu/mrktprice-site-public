"""Tiingo EOD price connector - a resilient FALLBACK behind yfinance.

yfinance is the audit's #1 fragility (an unofficial scraper that throttles/breaks with no
backup). Tiingo's free tier (~1000 req/day, ~50 symbols/hr) is enough to backfill closes
for names yfinance drops on a given night. Gated by ratelimit.Limiter('tiingo') so it can
never blow the free quota. Returns daily closes oldest->newest, or None.
"""
import os


def fetch_closes(ticker, days=260, sess=None, limiter=None):
    key = os.environ.get("TIINGO_API_KEY", "").strip()
    if not key:
        return None
    try:
        import requests
        import datetime as dt
        from ratelimit import Limiter
    except Exception:
        return None
    lim = limiter or Limiter("tiingo")
    if not lim.acquire():          # budget spent or breaker tripped -> skip cleanly
        return None
    start = (dt.date.today() - dt.timedelta(days=int(days * 1.6) + 10)).isoformat()
    s = sess or requests.Session()
    try:
        r = s.get("https://api.tiingo.com/tiingo/daily/%s/prices" % ticker.lower(),
                  params={"startDate": start, "token": key, "format": "json"}, timeout=20)
        if Limiter.is_limit(r.status_code, getattr(r, "text", "")):
            lim.trip("tiingo %s" % r.status_code)
            return None
        arr = r.json()
        if not isinstance(arr, list) or not arr:
            return None
        cl = [float(x["close"]) for x in arr if x.get("close") is not None]
        return cl[-days:] if len(cl) >= 30 else None
    except Exception:
        return None


def fetch_rows(ticker, days=4000, sess=None, limiter=None):
    """Daily history as [[YYYY-MM-DD, adjClose, volume], ...] oldest->newest, or None.
    Same shape emit_static.history() expects, so Tiingo can serve as an official-API
    fallback when yfinance (an unofficial scraper) drops a name. Gated on TIINGO_API_KEY."""
    key = os.environ.get("TIINGO_API_KEY", "").strip()
    if not key:
        return None
    try:
        import requests
        import datetime as dt
        from ratelimit import Limiter
    except Exception:
        return None
    lim = limiter or Limiter("tiingo")
    if not lim.acquire():
        return None
    start = (dt.date.today() - dt.timedelta(days=int(days) + 10)).isoformat()
    s = sess or requests.Session()
    try:
        r = s.get("https://api.tiingo.com/tiingo/daily/%s/prices" % ticker.lower(),
                  params={"startDate": start, "token": key, "format": "json"}, timeout=20)
        if Limiter.is_limit(r.status_code, getattr(r, "text", "")):
            lim.trip("tiingo %s" % r.status_code)
            return None
        arr = r.json()
        if not isinstance(arr, list) or not arr:
            return None
        rows = []
        for x in arr:
            d = x.get("date")
            c = x.get("adjClose", x.get("close"))   # split/div-adjusted to match FMP/yfinance auto_adjust
            v = x.get("adjVolume", x.get("volume")) or 0
            if d and c is not None:
                try:
                    rows.append([str(d)[:10], round(float(c), 4), int(float(v))])
                except Exception:
                    continue
        return rows if len(rows) >= 40 else None
    except Exception:
        return None


__all__ = ["fetch_closes", "fetch_rows"]
