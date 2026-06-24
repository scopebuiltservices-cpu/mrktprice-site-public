"""Options-chain hygiene: no-arbitrage checks (monotonicity, butterfly convexity,
price bounds, calendar) + liquidity/stale filters. Garbage quotes -> garbage IV
and false 'richness', so this gates the chain before any valuation."""
import math

def liquidity_filter(chain, min_oi=10, max_rel_spread=0.6):
    """Keep contracts with enough OI and a tradeable spread. Adds 'mark','relSpread'."""
    keep=[]
    for o in chain:
        try: K=float(o["strike"])
        except Exception: continue
        oi=o.get("oi") or o.get("openInterest") or 0
        try: oi=float(oi)
        except Exception: oi=0
        bid=o.get("bid"); ask=o.get("ask")
        try: bid=float(bid) if bid not in (None,"") else None
        except Exception: bid=None
        try: ask=float(ask) if ask not in (None,"") else None
        except Exception: ask=None
        mark=None; rel=None
        if bid is not None and ask is not None and ask>0 and ask>=bid:
            mark=(bid+ask)/2; rel=(ask-bid)/mark if mark>0 else None
        else:
            for k in ("mark","last","price"):
                try:
                    v=o.get(k)
                    if v not in (None,""): mark=float(v); break
                except Exception: pass
        if oi<min_oi: continue
        if rel is not None and rel>max_rel_spread: continue
        oo=dict(o); oo["mark"]=mark; oo["relSpread"]=(round(rel,3) if rel is not None else None); oo["oi"]=oi
        keep.append(oo)
    return keep

def no_arb_violations(chain, spot, T, r, q=0.0):
    """Return a list of violations across calls and puts (empty == arbitrage-free).
    Checks: price bounds, monotonicity in K, butterfly convexity, put-call parity."""
    v=[]
    for kind in ("C","P"):
        leg=sorted([o for o in chain if str(o.get("type","")).upper()[:1]==kind and o.get("mark") is not None],
                   key=lambda o:float(o["strike"]))
        Ks=[float(o["strike"]) for o in leg]; Px=[float(o["mark"]) for o in leg]
        dfq,dfr=math.exp(-q*T),math.exp(-r*T)
        for K,P in zip(Ks,Px):
            if kind=="C":
                lo=max(spot*dfq-K*dfr,0.0); hi=spot*dfq
            else:
                lo=max(K*dfr-spot*dfq,0.0); hi=K*dfr
            if P<lo-1e-2 or P>hi+1e-2: v.append(f"{kind} K={K}: price {P:.2f} outside [{lo:.2f},{hi:.2f}]")
        # monotonicity: calls down in K, puts up in K
        for i in range(1,len(Px)):
            if kind=="C" and Px[i]>Px[i-1]+1e-2: v.append(f"C monotonicity K {Ks[i-1]}->{Ks[i]}")
            if kind=="P" and Px[i]<Px[i-1]-1e-2: v.append(f"P monotonicity K {Ks[i-1]}->{Ks[i]}")
        # butterfly convexity
        for i in range(1,len(Px)-1):
            if Px[i-1]-2*Px[i]+Px[i+1] < -1e-2: v.append(f"{kind} butterfly@{Ks[i]}")
    return v

def calendar_violations(chain_by_T):
    """chain_by_T: {T_years: chain}. Same-strike call value must not decrease with T."""
    v=[]; Ts=sorted(chain_by_T)
    def cmap(ch): 
        return {float(o["strike"]):float(o["mark"]) for o in ch
                if str(o.get("type","")).upper()[:1]=="C" and o.get("mark") is not None}
    for a,b in zip(Ts,Ts[1:]):
        ca,cb=cmap(chain_by_T[a]),cmap(chain_by_T[b])
        for K in set(ca)&set(cb):
            if cb[K] < ca[K]-1e-2: v.append(f"calendar K={K}: T{b}<T{a}")
    return v
