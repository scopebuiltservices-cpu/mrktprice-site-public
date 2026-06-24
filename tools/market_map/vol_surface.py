"""Gatheral raw-SVI implied-vol slice: total variance w(k)=a+b(rho(k-m)+sqrt((k-m)^2+sigma^2)),
k=log(K/F). Calibrated by Nelder-Mead. Yields ATM vol/skew/curvature, term-structure slope,
and Gatheral's butterfly no-arbitrage check g(k)>=0. Pure stdlib."""
import math

def svi_w(k,p):
    a,b,rho,m,s=p
    return a+b*(rho*(k-m)+math.sqrt((k-m)**2+s*s))

def _nelder_mead(f,x0,steps,iters=400,tol=1e-10):
    n=len(x0); simplex=[list(x0)]
    for i in range(n):
        y=list(x0); y[i]+=steps[i]; simplex.append(y)
    fv=[f(p) for p in simplex]
    for _ in range(iters):
        order=sorted(range(n+1),key=lambda i:fv[i]); simplex=[simplex[i] for i in order]; fv=[fv[i] for i in order]
        if abs(fv[-1]-fv[0])<tol: break
        cen=[sum(simplex[i][j] for i in range(n))/n for j in range(n)]
        xr=[cen[j]+1.0*(cen[j]-simplex[-1][j]) for j in range(n)]; fr=f(xr)
        if fr<fv[0]:
            xe=[cen[j]+2.0*(cen[j]-simplex[-1][j]) for j in range(n)]; fe=f(xe)
            simplex[-1],fv[-1]=(xe,fe) if fe<fr else (xr,fr)
        elif fr<fv[-2]:
            simplex[-1],fv[-1]=xr,fr
        else:
            xc=[cen[j]+0.5*(simplex[-1][j]-cen[j]) for j in range(n)]; fc=f(xc)
            if fc<fv[-1]: simplex[-1],fv[-1]=xc,fc
            else:
                for i in range(1,n+1):
                    simplex[i]=[simplex[0][j]+0.5*(simplex[i][j]-simplex[0][j]) for j in range(n)]; fv[i]=f(simplex[i])
    i=min(range(n+1),key=lambda i:fv[i]); return simplex[i],fv[i]

def calibrate_svi(ks, ws, weights=None):
    """ks=log-moneyness, ws=market total variances. Returns (params, rmse)."""
    if len(ks)<5: return None
    w0=weights or [1.0]*len(ks)
    def obj(p):
        a,b,rho,m,s=p
        pen=0.0
        if b<=0: pen+=1e3*(1-b)
        if s<=1e-4: pen+=1e3*(1e-4-s)
        if abs(rho)>=0.999: pen+=1e3*(abs(rho)-0.999)
        e=0.0
        for k,wm,wt in zip(ks,ws,w0):
            wv=a+b*(rho*(k-m)+math.sqrt((k-m)**2+s*s))
            if wv<0: pen+=1e3*(-wv)
            e+=wt*(wv-wm)**2
        return e+pen
    atm=sum(ws)/len(ws)
    x0=[max(min(ws),1e-4),0.1,-0.3,0.0,0.1]
    p,err=_nelder_mead(obj,x0,[0.02,0.05,0.1,0.05,0.05],iters=800)
    rmse=math.sqrt(sum((svi_w(k,p)-wm)**2 for k,wm in zip(ks,ws))/len(ks))
    return p,rmse

def slice_features(p,T):
    a,b,rho,m,s=p
    w0=svi_w(0.0,p)
    dwdk=b*(rho+(-m)/math.sqrt(m*m+s*s))           # ATM skew (in total variance)
    d2=b*(s*s)/((m*m+s*s)**1.5)                     # curvature at k=0
    atm_vol=math.sqrt(max(w0,0)/T) if T>0 else None
    # Gatheral butterfly no-arb: g(k) >= 0 on a grid
    def g(k):
        w=svi_w(k,p)
        wp=b*(rho+(k-m)/math.sqrt((k-m)**2+s*s))
        wpp=b*(s*s)/(((k-m)**2+s*s)**1.5)
        return (1-k*wp/(2*w))**2 - (wp*wp/4)*(1/w+0.25) + wpp/2
    arb_free=all(g(k)>=-1e-6 for k in [x/10 for x in range(-20,21)])
    return {"atmVol":round(atm_vol,4) if atm_vol else None,
            "atmTotalVar":round(w0,6),"atmSkew":round(dwdk,4),"curvature":round(d2,4),
            "butterflyArbFree":bool(arb_free)}

def term_slope(atm_vols_by_T):
    """ATM-vol term-structure slope (per year). atm_vols_by_T: {T: atm_vol}."""
    pts=sorted(atm_vols_by_T.items())
    if len(pts)<2: return None
    (t0,v0),(t1,v1)=pts[0],pts[-1]
    return round((v1-v0)/(t1-t0),4)
