"""Free-to-compute options/gamma engine for MrktPrice — dealer Gamma Exposure (GEX), gamma walls,
zero-gamma flip, ATM implied vol, straddle expected move, put/call ratio, IV skew, +/-GEX regime.

Pure stdlib math. Feed it an options chain (EODHD or any source) as a list of dicts:
  {strike, type:'C'|'P', oi, iv (decimal, e.g. 0.30), gamma (optional)}
If gamma is absent it's computed from Black-Scholes using iv/spot/strike/T. Research only.
"""
import math, datetime

SQRT2PI = math.sqrt(2*math.pi)
def _npdf(x): return math.exp(-0.5*x*x)/SQRT2PI

def bs_gamma(spot, strike, t_years, iv, r=0.04, q=0.0):
    """Black-Scholes gamma (same for calls/puts). Returns 0 on degenerate inputs."""
    if spot<=0 or strike<=0 or t_years<=0 or iv<=0: return 0.0
    srt = iv*math.sqrt(t_years)
    if srt<=0: return 0.0
    d1 = (math.log(spot/strike) + (r-q+0.5*iv*iv)*t_years)/srt
    return math.exp(-q*t_years)*_npdf(d1)/(spot*srt)

def _interp_zero(xs, ys):
    """Find x where y crosses zero (linear interp on the first sign change). None if no crossing."""
    for i in range(1, len(xs)):
        y0, y1 = ys[i-1], ys[i]
        if y0==0: return xs[i-1]
        if (y0<0) != (y1<0):
            if y1==y0: return xs[i]
            return xs[i-1] + (xs[i]-xs[i-1])*(0-y0)/(y1-y0)
    return None

def _contract_T(o, default_T):
    """Time-to-expiry in YEARS for this contract: prefer explicit days/dte, else parse exp date,
    else the chain-level default. Fixes the bug of pricing every strike at one maturity."""
    for k in ("days","dte"):
        v=o.get(k)
        try:
            if v not in (None,""):
                d=float(v)
                if d>0: return d/365.0
        except Exception: pass
    e=o.get("exp")
    if e:
        try:
            d=(datetime.date.fromisoformat(str(e)[:10])-datetime.date.today()).days
            if d>0: return d/365.0
        except Exception: pass
    return default_T

def _iv_ok(iv):
    """Sanity bounds: a usable implied vol is positive and below 300% (deep-ITM/illiquid
    EOD quotes routinely report absurd IVs that would poison ATM-IV, skew and expected-move)."""
    return iv is not None and 0.0 < iv < 3.0

def compute_gex(chain, spot, days, r=0.04, contract=100):
    """Dealer GEX profile. Convention: dealers long calls / short puts (SqueezeMetrics-style) ->
    callGamma adds +, putGamma adds - to dealer gamma. Each contract is priced at its OWN
    time-to-expiry; IVs are sanity-bounded. Returns a compact dict, or None if no usable data."""
    if not chain or spot<=0: return None
    default_T = max(days,1)/365.0
    per = {}                                   # strike -> {cG,pG,cOI,pOI}
    cIVs=[]; pIVs=[]; Tfront=None
    for o in chain:
        try:
            K=float(o["strike"]); typ=str(o.get("type","")).upper()[:1]; oi=float(o.get("oi") or 0)
        except Exception: continue
        if K<=0 or oi<=0 or typ not in ("C","P"): continue
        Ti=_contract_T(o, default_T)
        if Ti>0 and (Tfront is None or Ti<Tfront): Tfront=Ti
        iv=o.get("iv")
        try: iv=float(iv) if iv not in (None,"") else None
        except Exception: iv=None
        ivok=_iv_ok(iv)
        g=o.get("gamma")
        try: g=float(g) if g not in (None,"") else None
        except Exception: g=None
        if g is None: g=bs_gamma(spot,K,Ti,iv if ivok else 0.3,r)   # per-contract maturity
        d=per.setdefault(K,{"cG":0.0,"pG":0.0,"cOI":0.0,"pOI":0.0})
        if typ=="C": d["cG"]+=g*oi; d["cOI"]+=oi; ivok and cIVs.append((abs(K-spot),iv))
        else:        d["pG"]+=g*oi; d["pOI"]+=oi; ivok and pIVs.append((abs(K-spot),iv))
    if not per: return None
    Tfront=Tfront or default_T
    Ks=sorted(per)
    dealer=[(per[K]["cG"]-per[K]["pG"])*contract for K in Ks]
    gex1=[g*spot*spot*0.01 for g in dealer]                       # $ per 1% move at each strike
    gex_total=sum(gex1)
    mag=[((per[K]["cG"]+per[K]["pG"])*contract, K) for K in Ks]
    up=[(m,K) for (m,K) in mag if K>=spot]; dn=[(m,K) for (m,K) in mag if K<spot]
    wall_up=max(up)[1] if up else None; wall_dn=max(dn)[1] if dn else None
    cum=[]; s=0.0
    for g in gex1: s+=g; cum.append(s)
    flip=_interp_zero(Ks, cum)
    atm_iv=None
    allIV=sorted(cIVs+pIVs)
    if allIV: atm_iv=allIV[0][1]
    exp_move=(atm_iv*math.sqrt(Tfront)) if atm_iv else None        # uses the NEAREST expiry, not a fixed horizon
    cOI=sum(per[K]["cOI"] for K in Ks); pOI=sum(per[K]["pOI"] for K in Ks)
    pcr=round(pOI/cOI,2) if cOI>0 else None
    def _otm_iv(lst): return (sorted(lst)[len(lst)//2][1] if lst else None)
    pv=_otm_iv([(d,iv) for (d,iv) in pIVs]); cv=_otm_iv([(d,iv) for (d,iv) in cIVs])
    skew=round((pv-cv),3) if (pv is not None and cv is not None) else None
    return {
        "gexTotal": round(gex_total),
        "regime": ("positive (pinning/mean-revert)" if gex_total>0 else "negative (amplifying/trend)"),
        "wallUp": wall_up, "wallDn": wall_dn, "flip": round(flip,2) if flip is not None else None,
        "atmIV": round(atm_iv*100,1) if atm_iv else None,
        "expMovePct": round(exp_move*100,2) if exp_move else None,
        "frontDays": round(Tfront*365),
        "pcr": pcr, "skew": skew, "days": days,
    }
