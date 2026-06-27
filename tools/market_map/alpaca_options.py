"""Gated Alpaca options fetch -> Black-Scholes fair value / greeks / market-richness
(black_scholes) and dealer GEX (options_gex), both from the SAME ticker's spot and
realized vol. Mirrors eodhd_options.enrich_options() so build_market_map can use it as a
drop-in fallback. Runs only when ALPACA_API_KEY_ID + ALPACA_API_SECRET_KEY are set. Research only.

DATA SOURCE: Alpaca "Option chain" snapshots — GET
  https://data.alpaca.markets/v1beta1/options/snapshots/{UNDERLYING}
Each snapshot carries latestQuote (bid/ask), latestTrade, impliedVolatility and greeks
(delta/gamma/theta/vega/rho). The free tier uses feed=indicative (delayed trades, modified
quotes); a paid subscription unlocks feed=opra. Open interest is NOT in the chain snapshot,
so GEX (which needs OI) degrades to None while the BS valuation/greeks/IV still populate.
The contract is identified by its OCC symbol (ROOT + YYMMDD + C/P + strike*1000), which we
parse for strike / type / expiry. With no keys set, enrich_options() returns None cleanly.
"""
import os, re, datetime
from options_gex import compute_gex
import black_scholes as _bs
import options_analytics as _oa
import chain_quality as _cq
import rate_curve as _rc
try: import bs_record as _rec
except Exception: _rec = None

_R = float(os.environ.get("MRKT_RISK_FREE", "0.04"))      # scalar fallback
_Q = float(os.environ.get("MRKT_DIV_YIELD", "0.0"))
_BASE = "https://data.alpaca.markets/v1beta1/options/snapshots/"
_FEED = os.environ.get("ALPACA_OPT_FEED", "indicative")   # free=indicative, paid=opra
_HORIZON_DAYS = int(os.environ.get("ALPACA_OPT_HORIZON_DAYS", "120"))  # cap expiries pulled
_MAX_PAGES = int(os.environ.get("ALPACA_OPT_MAX_PAGES", "6"))          # 1000 contracts/page
_MONEYNESS = float(os.environ.get("ALPACA_OPT_MONEYNESS", "0.40"))     # keep strikes within +/-40% of spot
_CURVE = None

# OCC option symbol: root (1-6 alnum) + YYMMDD + C/P + strike(8 digits, x1000)
_OCC = re.compile(r"^([A-Z0-9]{1,6})(\d{6})([CP])(\d{8})$")


def _rate(days):
    """Per-maturity risk-free from the curve (live FRED if MRKT_FETCH_CURVE=1, else static)."""
    global _CURVE
    try:
        if _CURVE is None:
            _CURVE = _rc.Curve(_rc.fetch_curve()) if os.environ.get("MRKT_FETCH_CURVE") == "1" else _rc.default_curve()
        return _CURVE.rate_for(max(days, 1) / 365.0)
    except Exception:
        return _R


def _f(x):
    try:
        if x in (None, ""):
            return None
        return float(x)
    except Exception:
        return None


def _parse_occ(sym):
    """(strike, 'C'|'P', expiry_date) from an OCC symbol, or (None,None,None)."""
    m = _OCC.match(str(sym or "").strip().upper())
    if not m:
        return None, None, None
    root, ymd, cp, strike8 = m.groups()
    try:
        exp = datetime.date(2000 + int(ymd[0:2]), int(ymd[2:4]), int(ymd[4:6]))
    except Exception:
        exp = None
    try:
        strike = int(strike8) / 1000.0
    except Exception:
        strike = None
    return strike, cp, exp


def _get(s, url, params=None, headers=None, timeout=30, tries=3):
    """GET with bounded retry/backoff on 429 / 5xx. Returns the final response."""
    import time
    r = None
    for i in range(tries):
        r = s.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code == 429 or 500 <= r.status_code < 600:
            if i == tries - 1:
                return r
            ra = r.headers.get("Retry-After") if hasattr(r, "headers") else None
            try:
                wait = float(ra) if ra else 1.5 * (2 ** i)
            except Exception:
                wait = 1.5 * (2 ** i)
            time.sleep(min(wait, 20))
            continue
        return r
    return r


def _fetch_chain(ticker, kid, ksec, spot, sess):
    """Pull the Alpaca option-chain snapshots for `ticker`, normalised to the flat shape the
    GEX/BS engines expect: {strike,type:'C'|'P',oi,iv,gamma,delta,bid,ask,last,exp,dte}.
    Filters to expiries within ALPACA_OPT_HORIZON_DAYS and strikes within +/-MONEYNESS of spot.
    Returns (chain, nearest_days_to_expiry)."""
    import requests
    s = sess or requests.Session()
    today = datetime.date.today()
    exp_lte = (today + datetime.timedelta(days=_HORIZON_DAYS)).isoformat()
    headers = {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": ksec}
    params = {"feed": _FEED, "limit": "1000", "expiration_date_lte": exp_lte}
    if spot and spot > 0:
        params["strike_price_gte"] = round(spot * (1 - _MONEYNESS), 2)
        params["strike_price_lte"] = round(spot * (1 + _MONEYNESS), 2)
    url = _BASE + str(ticker).upper()
    snaps = {}
    token = None
    for _ in range(_MAX_PAGES):
        p = dict(params)
        if token:
            p["page_token"] = token
        r = _get(s, url, params=p, headers=headers, timeout=30)
        if r.status_code in (401, 402, 403):
            return [], None
        try:
            j = r.json()
        except Exception:
            break
        chunk = (j or {}).get("snapshots") or {}
        for k, v in chunk.items():
            if k not in snaps:
                snaps[k] = v
        token = (j or {}).get("next_page_token")
        if not token or not chunk:
            break

    chain = []
    nearest = None
    for sym, snap in snaps.items():
        strike, cp, exp = _parse_occ(sym)
        if not strike or strike <= 0 or cp not in ("C", "P"):
            continue
        q = (snap or {}).get("latestQuote") or {}
        t = (snap or {}).get("latestTrade") or {}
        g = (snap or {}).get("greeks") or {}
        iv = _f((snap or {}).get("impliedVolatility"))
        bid, ask = _f(q.get("bp")), _f(q.get("ap"))
        last = _f(t.get("p"))
        dte = (exp - today).days if exp else None
        if dte is not None and dte <= 0:
            continue
        chain.append({
            "strike": strike, "type": cp,
            "oi": _f((snap or {}).get("openInterest")),   # usually absent in chain snapshot
            "iv": iv if (iv and iv > 0) else None,
            "gamma": _f(g.get("gamma")), "delta": _f(g.get("delta")),
            "bid": bid, "ask": ask,
            "last": last if last else ((bid + ask) / 2 if (bid is not None and ask is not None) else None),
            "exp": exp.isoformat() if exp else None, "dte": dte,
        })
        if dte and (nearest is None or dte < nearest):
            nearest = dte
    return chain, (int(nearest) if nearest else None)


def enrich_options(ticker, spot, closes=None, days=30, sess=None, record=True):
    """Returns {"gex":{...}|None, "bs":{summary}|None} or None. Mirrors eodhd_options."""
    kid = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    ksec = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
    if not kid or not ksec or not spot:
        return None
    try:
        chain, nearest = _fetch_chain(ticker, kid, ksec, spot, sess)
        if not chain:
            return None
        d = nearest or days
        try:
            clean = _cq.liquidity_filter(chain)
            if len(clean) < 4:
                clean = chain
        except Exception:
            clean = chain
        # GEX needs open interest; only compute when at least some OI is present
        gex = None
        try:
            if any((o.get("oi") or 0) for o in clean):
                gex = compute_gex(clean, spot, d)
        except Exception:
            gex = None
        r = _rate(d)
        summ = _oa.analyze(ticker, spot, closes, chain, d, r=r, record=record)
        if not summ:
            rv = _bs.realized_vol(closes) if closes else None
            v = _bs.value_chain(chain, spot, d, r=r, q=_Q, ref_vol=rv)
            summ = v["summary"] if v else None
        if summ is not None:
            summ["optSource"] = "alpaca:" + _FEED
        return {"gex": gex, "bs": summ}
    except Exception:
        return None


def fetch_gex(ticker, spot, days=30, sess=None):   # parity with eodhd_options
    r = enrich_options(ticker, spot, None, days, sess, record=False)
    return r["gex"] if r else None
