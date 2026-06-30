"""Risk-neutral analytics from an option strip:
 - Breeden-Litzenberger implied PDF  f(K)=e^{rT} d2C/dK2  (+ prob below/above)
 - model-free implied variance (CBOE VIX replication) and the variance-risk premium
 - Bakshi-Kapadia-Madan (2003) risk-neutral skewness & kurtosis.
Inputs are OTM option marks across strikes for one maturity. Pure stdlib."""
import math

def _otm_strip(chain, spot):
    """Return sorted [(K, Q)] using OTM options (puts below spot, calls above)."""
    by={}
    for o in chain:
        m=o.get("mark")
        if m is None: continue
        try: K=float(o["strike"]); kind=str(o.get("type","")).upper()[:1]
        except Exception: continue
        by.setdefault(K,{})[kind]=float(m)
    strip=[]
    for K in sorted(by):
        d=by[K]
        if K<spot and "P" in d: strip.append((K,d["P"]))
        elif K>spot and "C" in d: strip.append((K,d["C"]))
        elif "C" in d and "P" in d: strip.append((K,0.5*(d["C"]+d["P"])))
    return strip

def bl_density(call_strikes_prices, T, r, with_diag=False):
    """Breeden-Litzenberger: f(K)=e^{rT} * second difference of call price in K.

    NOTE: a raw second finite difference + clip-to-zero GUARANTEES a nonnegative normalized function but
    NOT that it came from an arbitrage-free call surface — clipping can hide local convexity (butterfly)
    violations rather than fix the surface. We therefore measure the RAW negative-density mass share BEFORE
    clipping; a large share means the density is cosmetically repaired, not data-supported. Set with_diag=True
    to get {density, negMassShare, nConvexityViolations, arbConsistent}. Default returns the density list
    (backward-compatible)."""
    pts=sorted(call_strikes_prices)
    if len(pts)<3: return None
    Ks=[k for k,_ in pts]; Cs=[c for _,c in pts]; dfr=math.exp(r*T)
    raw=[]
    for i in range(1,len(Ks)-1):
        h1=Ks[i]-Ks[i-1]; h2=Ks[i+1]-Ks[i]
        d2=2*(Cs[i-1]/(h1*(h1+h2))-Cs[i]/(h1*h2)+Cs[i+1]/(h2*(h1+h2)))
        raw.append((Ks[i],dfr*d2))                                 # unclipped (may be negative)
    # diagnostic: |negative mass| / total |mass| before clipping, and count of convexity violations
    pos_mass=sum(abs(v) for _,v in raw if v>0); neg_mass=sum(-v for _,v in raw if v<0)
    tot=pos_mass+neg_mass
    neg_share=round(neg_mass/tot,4) if tot>0 else 0.0
    n_viol=sum(1 for _,v in raw if v<0)
    dens=[(k,max(v,0.0)) for k,v in raw]                           # clip for the usable density
    area=sum((dens[i+1][0]-dens[i][0])*(dens[i+1][1]+dens[i][1])/2 for i in range(len(dens)-1))
    if area>0: dens=[(k,v/area) for k,v in dens]
    if with_diag:
        return {"density":dens,"negMassShare":neg_share,"nConvexityViolations":n_viol,
                "arbConsistent":bool(n_viol==0)}
    return dens

def prob_below(dens, level):
    if not dens: return None
    s=0.0
    for i in range(len(dens)-1):
        k0,v0=dens[i]; k1,v1=dens[i+1]
        if k1<=level: s+=(k1-k0)*(v0+v1)/2
        elif k0<level<k1:
            t=(level-k0)/(k1-k0); vmid=v0+t*(v1-v0); s+=(level-k0)*(v0+vmid)/2
    return min(max(s,0.0),1.0)

def model_free_iv(chain, spot, T, r, forward=None):
    """CBOE/VIX model-free implied variance from the OTM strip."""
    strip=_otm_strip(chain,spot)
    if len(strip)<4: return None
    F=forward or spot*math.exp(r*T)
    Ks=[k for k,_ in strip]
    K0=max([k for k in Ks if k<=F], default=Ks[0])
    dfr=math.exp(r*T); s=0.0
    for i,(K,Q) in enumerate(strip):
        if i==0: dK=Ks[1]-Ks[0]
        elif i==len(strip)-1: dK=Ks[-1]-Ks[-2]
        else: dK=(Ks[i+1]-Ks[i-1])/2
        s+=(dK/(K*K))*dfr*Q
    var=(2.0/T)*s-(1.0/T)*((F/K0-1)**2)
    return {"mfImpliedVar":var,"mfImpliedVol":math.sqrt(var) if var>0 else None,"F":F,"K0":K0}

def variance_risk_premium(chain, spot, T, r, rv_forecast_var, forward=None):
    """VRP = model-free implied variance - forecast realized variance (HAR-RV).
    Positive => options expensive vs expected realized (sell-vol edge).
    `forward` MUST be threaded through so the implied variance here uses the SAME forward the summary
    reports for mfImpliedVolPct; otherwise mf and vrp silently use two different forwards (F=Se^{rT} here
    vs a parity forward upstream), which is a forward-inconsistency bug."""
    mf=model_free_iv(chain,spot,T,r,forward=forward)
    if not mf or rv_forecast_var is None: return None
    return {"impliedVar":round(mf["mfImpliedVar"],6),"forecastVar":round(rv_forecast_var,6),
            "vrp":round(mf["mfImpliedVar"]-rv_forecast_var,6),
            "vrpVolPts":round((math.sqrt(max(mf["mfImpliedVar"],0))-math.sqrt(max(rv_forecast_var,0)))*100,2)}

def bkm_moments(chain, spot, T, r):
    """Bakshi-Kapadia-Madan risk-neutral skewness & kurtosis from OTM options."""
    strip=_otm_strip(chain,spot)
    if len(strip)<5: return None
    Ks=[k for k,_ in strip]; erT=math.exp(r*T); V=W=X=0.0
    for i,(K,Q) in enumerate(strip):
        if i==0: dK=Ks[1]-Ks[0]
        elif i==len(strip)-1: dK=Ks[-1]-Ks[-2]
        else: dK=(Ks[i+1]-Ks[i-1])/2
        x=math.log(K/spot)
        V+=(2*(1-x)/(K*K))*Q*dK
        W+=((6*x-3*x*x)/(K*K))*Q*dK
        X+=((12*x*x-4*x*x*x)/(K*K))*Q*dK
    mu=erT-1-(erT/2)*V-(erT/6)*W-(erT/24)*X
    denom=(erT*V-mu*mu)
    if denom<=0: return None
    skew=(erT*W-3*mu*erT*V+2*mu**3)/denom**1.5
    kurt=(erT*X-4*mu*erT*W+6*erT*mu*mu*V-3*mu**4)/denom**2
    return {"rnSkew":round(skew,4),"rnKurt":round(kurt,4),"rnVol":round(math.sqrt(denom/T),4) if T>0 else None}
