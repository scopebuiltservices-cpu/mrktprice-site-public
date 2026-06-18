"""Gated EODHD options fetch -> options/gamma (GEX) via options_gex. Runs only when EODHD_API_KEY is set.
EODHD options API returns daily contracts with strike, type, open interest, IV and greeks. Research only."""
import os
from options_gex import compute_gex
def fetch_gex(ticker, spot, days=30, sess=None):
    key=os.environ.get("EODHD_API_KEY","").strip()
    if not key or not spot: return None
    try:
        import requests
        s=sess or requests.Session()
        # EODHD options endpoint (US): returns array of contracts with greeks
        url="https://eodhd.com/api/options/%s.US?api_token=%s&fmt=json"%(ticker,key)
        j=s.get(url,timeout=25).json()
        data=j.get("data") if isinstance(j,dict) else j
        chain=[]
        for c in (data or []):
            chain.append({"strike":c.get("strike"),"type":(c.get("type") or c.get("optionType") or "")[:1].upper(),
                          "oi":c.get("openInterest") or c.get("open_interest"),
                          "iv":c.get("impliedVolatility") or c.get("volatility"),
                          "gamma":c.get("gamma")})
        return compute_gex(chain, spot, days)
    except Exception:
        return None
