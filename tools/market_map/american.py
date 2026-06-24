"""American option pricing via Cox-Ross-Rubinstein binomial tree (early exercise,
continuous dividend yield q; discrete cash dividends via escrowed-spot adjustment).
US single-stock options are American, so route them here instead of European BSM."""
import math, black_scholes as bs

def crr_price(S,K,T,r,sigma,q=0.0,kind="C",steps=400,american=True):
    if S<=0 or K<=0 or T<=0 or sigma<=0:
        return bs._intrinsic(S,K,r,q,max(T,0.0),str(kind).upper()[:1])
    kind=str(kind).upper()[:1]
    dt=T/steps; u=math.exp(sigma*math.sqrt(dt)); d=1/u
    a=math.exp((r-q)*dt); p=(a-d)/(u-d)
    if p<=0 or p>=1:  # numerical guard -> fall back to European
        return bs.bs_price(S,K,T,r,sigma,q,kind)
    disc=math.exp(-r*dt)
    # terminal payoffs
    vals=[]
    for j in range(steps+1):
        ST=S*(u**j)*(d**(steps-j))
        vals.append(max(ST-K,0.0) if kind=="C" else max(K-ST,0.0))
    for i in range(steps-1,-1,-1):
        for j in range(i+1):
            cont=disc*(p*vals[j+1]+(1-p)*vals[j])
            if american:
                ST=S*(u**j)*(d**(i-j))
                ex=(ST-K) if kind=="C" else (K-ST)
                vals[j]=cont if cont>=ex else ex
            else:
                vals[j]=cont
    return vals[0]

def american_with_discrete_div(S,K,T,r,sigma,divs,kind="C",steps=400):
    """divs: list of (t_years, cash). Escrowed-dividend model: price on the
    PV-of-dividends-removed spot, which is the standard practical adjustment."""
    pv=sum(c*math.exp(-r*t) for (t,c) in (divs or []) if 0<t<=T)
    return crr_price(max(S-pv,1e-6),K,T,r,sigma,0.0,kind,steps,american=True)

def early_exercise_premium(S,K,T,r,sigma,q=0.0,kind="C",steps=400):
    return crr_price(S,K,T,r,sigma,q,kind,steps,True)-bs.bs_price(S,K,T,r,sigma,q,kind)
