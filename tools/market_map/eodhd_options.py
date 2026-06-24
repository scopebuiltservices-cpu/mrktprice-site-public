"""Gated EODHD options fetch -> (1) dealer GEX via options_gex and (2) Black-Scholes
fair value / greeks / market-richness via black_scholes, both from the SAME ticker's
spot and realized vol. Snapshots are logged to bs_record for calibration. Runs only
when EODHD_API_KEY is set. Research only.

NOTE ON DATA SOURCE (2025+): EODHD retired the legacy ``/api/options/{TICKER}.US``
endpoint. The current product is the UnicornBay "US Stock Options Data" feed at
``/api/mp/unicornbay/options/eod`` (JSON:API shape -- fields live under ``attributes``).
That feed is a SEPARATE add-on subscription; it is NOT included in EOD/All-World
Ultimate. With only the Ultimate plan (no options add-on) these calls return 402/403
and enrich_options() degrades to None -- prices/fundamentals still work, options don't.
"""
import os, datetime
from options_gex import compute_gex
import black_scholes as _bs
import options_analytics as _oa
import chain_quality as _cq
import rate_curve as _rc
try: import bs_record as _rec
except Exception: _rec = None

_R = float(os.environ.get("MRKT_RISK_FREE", "0.04"))   # scalar fallback
_Q = float(os.environ.get("MRKT_DIV_YIELD", "0.0"))
_BASE = "https://eodhd.com/api/mp/unicornbay/options/eod"
_LOOKBACK_DAYS = int(os.environ.get("EODHD_OPT_LOOKBACK_DAYS", "10"))  # bound history volume
_MAX_PAGES = int(os.environ.get("EODHD_OPT_MAX_PAGES", "8"))           # 1000 rows/page
_CURVE = None
def _rate(days):
    """Per-maturity risk-free from the curve (live FRED if MRKT_FETCH_CURVE=1, else static)."""
    global _CURVE
    try:
        if _CURVE is None:
            _CURVE = _rc.Curve(_rc.fetch_curve()) if os.environ.get("MRKT_FETCH_CURVE")=="1" else _rc.default_curve()
        return _CURVE.rate_for(max(days,1)/365.0)
    except Exception:
        return _R

def _f(x):
    try:
        if x in (None, ""): return None
        return float(x)
    except Exception:
        return None

def _get(s, url, params=None, timeout=30, tries=3):
    """GET with bounded retry/backoff on transient errors (429 rate-limit, 5xx). Respects
    Retry-After. Returns the final response so callers can still inspect 401/402/403."""
    import time
    r=None
    for i in range(tries):
        r=s.get(url, params=params, timeout=timeout)
        if r.status_code==429 or 500<=r.status_code<600:
            if i==tries-1: return r
            ra=r.headers.get("Retry-After") if hasattr(r,"headers") else None
            try: wait=float(ra) if ra else 1.5*(2**i)
            except Exception: wait=1.5*(2**i)
            time.sleep(min(wait,20)); continue
        return r
    return r

def _fetch_chain(ticker, key, sess):
    """Pull the current option chain for ``ticker`` from the UnicornBay EOD feed and
    normalise it to the flat shape the GEX/BS engines expect:
        {strike, type:'C'|'P', oi, iv(decimal), gamma, delta, bid, ask, last, exp}
    Only unexpired contracts (exp_date_from=today), only rows updated within
    EODHD_OPT_LOOKBACK_DAYS, newest first; keep the most-recent row per contract.
    Returns (chain, nearest_days_to_expiry)."""
    import requests
    s = sess or requests.Session()
    today = datetime.date.today()
    tfrom = (today - datetime.timedelta(days=_LOOKBACK_DAYS)).isoformat()
    params_base = {
        "filter[underlying_symbol]": ticker,
        "filter[exp_date_from]": today.isoformat(),
        "filter[tradetime_from]": tfrom,
        "sort": "-tradetime",
        "page[limit]": "1000",
        "api_token": key,
    }
    latest = {}
    offset = 0
    for _ in range(_MAX_PAGES):
        p = dict(params_base); p["page[offset]"] = str(offset)
        r = _get(s, _BASE, params=p, timeout=30)
        if r.status_code in (401, 402, 403):
            return [], None
        j = r.json()
        rows = j.get("data") if isinstance(j, dict) else None
        if not rows: break
        for row in rows:
            a = row.get("attributes") if isinstance(row, dict) else None
            if not a: continue
            c = a.get("contract") or row.get("id")
            if c and c not in latest:
                latest[c] = a
        meta = (j.get("meta") or {}) if isinstance(j, dict) else {}
        total = meta.get("total") or 0
        offset += len(rows)
        if offset >= total or len(rows) < 1000: break

    chain = []; nearest = None
    for a in latest.values():
        typ = str(a.get("type") or "")[:1].upper()
        if typ not in ("C", "P"): continue
        strike = _f(a.get("strike"))
        if not strike or strike <= 0: continue
        iv = _f(a.get("volatility"))
        chain.append({
            "strike": strike,
            "type": typ,
            "oi": _f(a.get("open_interest")),
            "iv": iv if (iv and iv > 0) else None,
            "gamma": _f(a.get("gamma")),
            "delta": _f(a.get("delta")),
            "bid": _f(a.get("bid")),
            "ask": _f(a.get("ask")),
            "last": _f(a.get("last")) or _f(a.get("midpoint")),
            "exp": a.get("exp_date"),
            "dte": _f(a.get("dte")),
        })
        dte = _f(a.get("dte"))
        if dte and dte > 0 and (nearest is None or dte < nearest):
            nearest = dte
    if nearest is None and chain:
        for o in chain:
            e = o.get("exp")
            if not e: continue
            try:
                d = (datetime.date.fromisoformat(e) - today).days
                if d > 0 and (nearest is None or d < nearest): nearest = d
            except Exception:
                pass
    return chain, (int(nearest) if nearest else None)

def enrich_options(ticker, spot, closes=None, days=30, sess=None, record=True):
    """Returns {"gex":{...}|None, "bs":{summary}|None}. Records a BS snapshot."""
    key = os.environ.get("EODHD_API_KEY", "").strip()
    if not key or not spot: return None
    try:
        chain, nearest = _fetch_chain(ticker, key, sess)
        if not chain: return None
        d = nearest or days
        try:
            clean = _cq.liquidity_filter(chain)
            if len(clean) < 4: clean = chain     # too thin after filtering -> use raw
        except Exception:
            clean = chain
        gex = compute_gex(clean, spot, d)        # GEX on the SAME cleaned chain analyze() uses
        r = _rate(d)
        summ = _oa.analyze(ticker, spot, closes, chain, d, r=r, record=record)
        if not summ:
            rv = _bs.realized_vol(closes) if closes else None
            v = _bs.value_chain(chain, spot, d, r=r, q=_Q, ref_vol=rv)
            summ = v["summary"] if v else None
        return {"gex": gex, "bs": summ}
    except Exception:
        return None

def fetch_gex(ticker, spot, days=30, sess=None):   # back-compat
    r = enrich_options(ticker, spot, None, days, sess, record=False)
    return r["gex"] if r else None
