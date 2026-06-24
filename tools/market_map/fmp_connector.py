"""Gated Financial Modeling Prep connector. Runs only when FMP_API_KEY is set; returns a price +
valuation dict (trailing/forward P/E, PEG, EV/EBITDA, EPS growth) for one ticker. Research only.

SMARTER KEY HANDLING (2026): probe_key() makes ONE classified validation call up front so the
build can fail fast with a precise, actionable reason — invalid key vs rate-limited vs plan/endpoint
— instead of silently hammering 150+ tickers with a dead key and reporting a vague "0 valuations".
FMP returns HTTP 200 with {"Error Message": ...} for invalid/over-limit/wrong-plan keys, so we
classify on the body, not just the status code."""
import os
STABLE = "https://financialmodelingprep.com/stable"
V3     = "https://financialmodelingprep.com/api/v3"

def _num(x):
    try:
        x=float(x); return x if (x==x and abs(x)<1e7) else None
    except Exception: return None

def _first(d, *keys):
    if not isinstance(d, dict): return None
    for k in keys:
        v=_num(d.get(k))
        if v is not None: return v
    return None

def _err_text(body):
    """Pull FMP's error string out of a 200-with-error-body or an object."""
    if isinstance(body, dict):
        for k in ("Error Message","error","message","errorMessage"):
            if body.get(k): return str(body[k])[:200]
    return ""

def classify(status, body):
    """Map (status, parsed body) -> (reason, message). reason in:
       ok | invalid_key | rate_limited | plan_or_endpoint | empty | http_error."""
    m=_err_text(body); low=m.lower()
    if "invalid api key" in low or "not valid" in low or status in (401,):
        return ("invalid_key", m or "HTTP %s"%status)
    if status==429 or "limit reach" in low or "rate limit" in low or "too many requests" in low or "bandwidth" in low:
        return ("rate_limited", m or "HTTP 429 / limit")
    if status in (402,403) or "not available" in low or "legacy" in low or "exclusive" in low or ("plan" in low and "upgrade" in low) or "subscription" in low:
        return ("plan_or_endpoint", m or "HTTP %s"%status)
    if isinstance(body, list) and body:
        return ("ok","")
    if isinstance(body, dict) and not m and body:
        return ("ok","")   # some stable endpoints return a single object
    if 200<=status<300:
        return ("empty", m or "empty response")
    return ("http_error", m or "HTTP %s"%status)

def _get(s, url, timeout=20, tries=3):
    import time
    r=None
    for i in range(tries):
        r=s.get(url, timeout=timeout)
        if r.status_code==429 or 500<=r.status_code<600:
            if i==tries-1: return r
            ra=r.headers.get("Retry-After") if hasattr(r,"headers") else None
            try: wait=float(ra) if ra else 1.5*(2**i)
            except Exception: wait=1.5*(2**i)
            time.sleep(min(wait,20)); continue
        return r
    return r

def probe_key(sess=None, ticker="AAPL"):
    """ONE up-front validation call. Returns {ok, reason, message, base}.
    Lets the caller skip the whole enrichment loop (and 150+ wasted calls) when the key is dead,
    and report exactly WHY so the fix is unambiguous."""
    key=os.environ.get("FMP_API_KEY","").strip()
    if not key:
        return {"ok":False,"reason":"missing","message":"FMP_API_KEY env var not set","base":None}
    try:
        import requests
    except Exception as e:
        return {"ok":False,"reason":"no_requests","message":str(e)[:120],"base":None}
    s=sess or requests.Session()
    last=("empty","no response",None)
    for base in (STABLE, V3):
        try:
            url=("%s/quote?symbol=%s&apikey=%s"%(base,ticker,key)) if base==STABLE else ("%s/quote/%s?apikey=%s"%(base,ticker,key))
            r=_get(s, url, timeout=20)
            try: body=r.json()
            except Exception: body=r.text
            reason,msg=classify(r.status_code, body)
            if reason=="ok":
                return {"ok":True,"reason":"ok","message":"","base":base}
            # invalid key / rate limit are definitive — same answer on every base, stop early
            if reason in ("invalid_key","rate_limited"):
                return {"ok":False,"reason":reason,"message":msg,"base":base}
            last=(reason,msg,base)
        except Exception as e:
            last=("network",str(e)[:120],base)
    return {"ok":False,"reason":last[0],"message":last[1],"base":last[2]}

def parse_val(quote, ratios, est):
    q=(quote or [{}])[0] if quote else {}
    rt=(ratios or [{}])[0] if ratios else {}
    e=(est or [{}])[0] if est else {}
    price=_first(q,"price")
    pe=_first(q,"pe") or _first(rt,"priceToEarningsRatioTTM","peRatioTTM","priceEarningsRatioTTM")
    evb=_first(rt,"enterpriseValueMultipleTTM","enterpriseValueToEBITDATTM","evToEBITDATTM")
    peg=_first(rt,"priceToEarningsGrowthRatioTTM","priceEarningsToGrowthRatioTTM","pegRatioTTM") or _first(q,"pegRatio")
    fe=_first(e,"epsAvg","estimatedEpsAvg")
    eps=_first(q,"eps")
    fpe=None; epsg=None
    if fe and price and fe>0: fpe=round(price/fe,1)
    if eps and fe and eps!=0: epsg=round((fe-eps)/abs(eps),3)
    return {"price":price,
            "val":{"pe":round(pe,1) if pe else None,"fpe":fpe,"peg":round(peg,2) if peg else None,
                   "evb":round(evb,1) if evb else None,"epsg":epsg,"revg":None}}

def _pull(base, ticker, key, sess):
    import requests
    s=sess or requests.Session()
    if base==STABLE:
        g=lambda slug:_get(s,"%s/%s?symbol=%s&apikey=%s"%(base,slug,ticker,key),timeout=20)
    else:
        g=lambda slug:_get(s,"%s/%s/%s?apikey=%s"%(base,slug,ticker,key),timeout=20)
    rq=g("quote")
    quote=rq.json()
    reason,msg=classify(rq.status_code, quote)
    if reason!="ok":
        raise RuntimeError("FMP %s [%s]: %s"%(base.split('/')[-1], reason, msg or "no data"))
    # ratios-ttm + analyst-estimates are BEST-EFFORT: a missing/erroring secondary endpoint must NOT
    # void the quote-based valuation (quote already carries price/pe/eps). This is why a valid key
    # was returning 0 usable valuations — one secondary endpoint erroring killed the whole row.
    def _opt(slug):
        try:
            b=g(slug).json()
            return b if isinstance(b, list) else []
        except Exception:
            return []
    ratios=_opt("ratios-ttm")
    est=_opt("analyst-estimates")
    return quote, ratios, est

def fetch(ticker, sess=None):
    key=os.environ.get("FMP_API_KEY","").strip()
    if not key: return None
    for base in (STABLE, V3):
        try:
            quote, ratios, est=_pull(base, ticker, key, sess)
            out=parse_val(quote, ratios, est)
            if out and out.get("price") is not None:
                return out
        except Exception:
            continue
    return None

__all__=["fetch","probe_key","classify","parse_val"]

if __name__=="__main__":
    # Self-test: `FMP_API_KEY=xxx python fmp_connector.py`  ->  one-line verdict on the key.
    import sys
    p=probe_key()
    tag="VALID ✓" if p.get("ok") else "NOT USABLE ✗"
    sys.stderr.write("FMP key probe: %s | reason=%s | %s\n"%(tag, p.get("reason"), p.get("message") or "(ok)"))
    sys.exit(0 if p.get("ok") else 1)
