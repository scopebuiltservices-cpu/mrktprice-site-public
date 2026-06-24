"""Implied forward and dividend/borrow extracted from put-call parity on the chain:
  C - P = e^{-rT}(F - K)   ->   regress (C-P) vs K: slope=-e^{-rT}, intercept=e^{-rT} F.
Then implied continuous yield q from  F = S e^{(r-q)T}. Free, and exposes hard-to-borrow."""
import math

def implied_forward(chain, spot, T, r):
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
    return {"forward":round(F,4),"impliedDivYield":round(q_imp,4) if q_imp is not None else None,
            "basisPct":round(100*(F/spot-1),3) if spot>0 else None,
            "slope":round(slope,4),"slopeExpected":round(-dfr,4),
            "hardToBorrow":(q_imp is not None and q_imp>0.05),  # high implied carry => borrow cost
            "pairs":len(xs)}
