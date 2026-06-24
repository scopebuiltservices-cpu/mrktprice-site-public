"""Higher-order / cross greeks, risk-neutral probabilities, and a fast IV seed,
built on the verified black_scholes pricer. The cross-greeks are exact derivatives
of the closed form, computed by central finite differences of the verified pricer
(robust, no sign-convention bugs) and checked in tests against closed-form identities."""
import math, black_scholes as bs

def prob_itm(S, K, T, r, sigma, q=0.0, kind="C"):
    """Risk-neutral probability of finishing in the money = N(d2) (calls) / N(-d2)."""
    if S<=0 or K<=0 or T<=0 or sigma<=0: return None
    d1,d2 = bs._d1_d2(S,K,T,r,sigma,q)
    return bs.norm_cdf(d2) if str(kind).upper()[:1]=="C" else bs.norm_cdf(-d2)

def _P(S,K,T,r,sig,q,kind): return bs.bs_price(S,K,T,r,sig,q,kind)

def greeks_ext(S,K,T,r,sigma,q=0.0,kind="C"):
    """First + second-order greeks. delta/gamma/vega/theta/rho from closed form;
    vanna/volga/charm/speed/color/zomma/veta/dual_delta by verified differentiation.
    vega/volga/vanna scaled to per-1-vol; *0.01 for per-vol-point at call site."""
    g = bs.greeks(S,K,T,r,sigma,q,kind)
    hS=1e-4*S; hv=1e-4; hT=1e-4
    d_S = lambda f: (f(S+hS)-f(S-hS))/(2*hS)
    # vanna = d(delta)/d(sigma) ; volga = d(vega)/d(sigma) ; charm = -d(delta)/dT ; veta = -d(vega)/dT
    dlt = lambda s,sg=sigma,T_=T: bs.greeks(s,K,T_,r,sg,q,kind)["delta"]
    veg = lambda s,sg=sigma,T_=T: bs.greeks(s,K,T_,r,sg,q,kind)["vega"]
    gam = lambda s,sg=sigma,T_=T: bs.greeks(s,K,T_,r,sg,q,kind)["gamma"]
    vanna=(dlt(S,sigma+hv)-dlt(S,sigma-hv))/(2*hv)
    volga=(veg(S,sigma+hv)-veg(S,sigma-hv))/(2*hv)
    zomma=(gam(S,sigma+hv)-gam(S,sigma-hv))/(2*hv)
    speed=(gam(S+hS)-gam(S-hS))/(2*hS)
    charm=-(dlt(S,sigma,T+hT)-dlt(S,sigma,T-hT))/(2*hT)
    veta =-(veg(S,sigma,T+hT)-veg(S,sigma,T-hT))/(2*hT)
    color=-(gam(S,sigma,T+hT)-gam(S,sigma,T-hT))/(2*hT)
    d1,d2=bs._d1_d2(S,K,T,r,sigma,q)
    dual_delta=(-math.exp(-r*T)*bs.norm_cdf(d2)) if str(kind).upper()[:1]=="C" else (math.exp(-r*T)*bs.norm_cdf(-d2))
    g.update({"vanna":vanna,"volga":volga,"zomma":zomma,"speed":speed,
              "charm":charm,"veta":veta,"color":color,"dualDelta":dual_delta,
              "probITM":prob_itm(S,K,T,r,sigma,q,kind)})
    return g

def implied_vol_fast(price,S,K,T,r,q=0.0,kind="C",tol=1e-9,max_iter=60):
    """Halley's method (uses vega+volga) with a Brenner-Subrahmanyam ATM seed;
    falls back to the robust solver. Faster, fewer iterations."""
    if price is None or S<=0 or K<=0 or T<=0 or price<=0: return None
    intr=bs._intrinsic(S,K,r,q,T,kind)
    cap=(S*math.exp(-q*T)) if str(kind).upper()[:1]=="C" else (K*math.exp(-r*T))
    if price<intr-1e-9 or price>cap+1e-9: return None
    sig=max(1e-3, math.sqrt(2*math.pi/T)*price/S)     # Brenner-Subrahmanyam ATM seed
    for _ in range(max_iter):
        diff=bs.bs_price(S,K,T,r,sig,q,kind)-price
        if abs(diff)<tol: return sig
        ge=greeks_ext(S,K,T,r,sig,q,kind)
        v=ge["vega"]; vo=ge["volga"]
        if v<1e-12: break
        denom=1-0.5*(diff/v)*(vo/v)                    # Halley correction
        sig-=(diff/v)/(denom if abs(denom)>1e-6 else 1.0)
        if sig<=1e-6 or sig>10: break
    return bs.implied_vol(price,S,K,T,r,q,kind,tol)
