"""Gated Financial Modeling Prep connector. Runs only when FMP_API_KEY is set; returns a price +
valuation dict (trailing/forward P/E, PEG, EV/EBITDA, earnings/rev growth) for one ticker. Research only."""
import os
BASE="https://financialmodelingprep.com/api/v3"
def _num(x):
    try:
        x=float(x); return x if (x==x and abs(x)<1e7) else None
    except Exception: return None
def parse_val(quote, ratios, est):
    """Map FMP responses -> the val dict shape the engine uses. Pure (testable without network)."""
    q=(quote or [{}])[0] if quote else {}
    rt=(ratios or [{}])[0] if ratios else {}
    pe=_num(q.get("pe")) or _num(rt.get("priceEarningsRatioTTM"))
    evb=_num(rt.get("enterpriseValueMultipleTTM")) or _num(rt.get("evToEBITDATTM"))
    peg=_num(rt.get("priceEarningsToGrowthRatioTTM")) or _num(q.get("pegRatio"))
    eps=_num(q.get("eps")); fpe=None; epsg=None
    e=(est or [{}])[0] if est else {}
    fe=_num(e.get("estimatedEpsAvg"))
    price=_num(q.get("price"))
    if fe and price and fe>0: fpe=round(price/fe,1)
    if eps and fe and eps!=0: epsg=round((fe-eps)/abs(eps),3)
    revg=None
    return {"price":price,
            "val":{"pe":round(pe,1) if pe else None,"fpe":fpe,"peg":round(peg,2) if peg else None,
                   "evb":round(evb,1) if evb else None,"epsg":epsg,"revg":revg}}
def fetch(ticker, sess=None):
    key=os.environ.get("FMP_API_KEY","").strip()
    if not key: return None
    try:
        import requests
        s=sess or requests.Session()
        g=lambda p:s.get("%s/%s/%s?apikey=%s"%(BASE,p,ticker,key),timeout=20).json()
        return parse_val(g("quote"), g("ratios-ttm"), g("analyst-estimates"))
    except Exception:
        return None
