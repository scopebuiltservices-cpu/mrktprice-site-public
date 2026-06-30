"""Implied forward and dividend/borrow extracted from put-call parity on the chain:
  C - P = e^{-rT}(F - K)   ->   regress (C-P) vs K: slope=-e^{-rT}, intercept=e^{-rT} F.
Then implied continuous yield q from  F = S e^{(r-q)T}. Free, and exposes hard-to-borrow.

EXERCISE-STYLE FIREWALL: the equality C - P = e^{-rT}(F - K) is EXACT only for EUROPEAN options. For
American single-name equity options (the OCC-cleared default) early-exercise premia E_C, E_P make
  C_A - P_A = Se^{-qT} - Ke^{-rT} + (E_C - E_P),
so the parity intercept recovers F only up to the discounted early-exercise spread e^{rT}(E_C - E_P), and the
implied dividend yield is biased by the same term. We therefore tag the output with `style`/`europeanValid`
and mark `impliedDivYieldValid`; consumers must NOT override a user-supplied q from an American chain."""
import math

def implied_forward(chain, spot, T, r, style="american"):
    """style: 'european' (cash-settled index) makes the parity identity exact; 'american' (single-name
    default) flags the forward/dividend as a biased heuristic (europeanValid=False)."""
    pairs={}
    for o in chain:
        m=o.get("mark")
        if m is None: continue
        try: K=float(o["strike"]); kind=str(o.get("type","")).upper()[:1]
        except Exception: continue
        pairs.setdefault(K,{})[kind]=float(m)
    xs=[]; ys=[]
    for K,d in pairs.items():
        if "C" in d and "P" in d: xs.append(K); ys.append(d["C"]-d["P"])
    if len(xs)<3: return None
    n=len(xs); sx=sum(xs); sy=sum(ys); sxx=sum(x*x for x in xs); sxy=sum(x*y for x,y in zip(xs,ys))
    den=n*sxx-sx*sx
    if abs(den)<1e-9: return None
    slope=(n*sxy-sx*sy)/den; intercept=(sy-slope*sx)/n
    dfr=math.exp(-r*T)
    # slope should be ~ -dfr; F = intercept/dfr
    F=intercept/dfr
    q_imp=r-math.log(F/spot)/T if (F>0 and spot>0 and T>0) else None
    european_valid = str(style).lower() == "european"
    return {"forward":round(F,4),"impliedDivYield":round(q_imp,4) if q_imp is not None else None,
            "basisPct":round(100*(F/spot-1),3) if spot>0 else None,
            "slope":round(slope,4),"slopeExpected":round(-dfr,4),
            "hardToBorrow":(q_imp is not None and q_imp>0.05),  # high implied carry => borrow cost
            "style":str(style).lower(),
            "europeanValid":european_valid,             # parity identity exact only for European exercise
            "impliedDivYieldValid":european_valid,      # do NOT override user q from an American chain
            "pairs":len(xs)}
