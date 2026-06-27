#!/usr/bin/env python3
"""Pooled cross-sectional research estimators (pure stdlib).

Closes the methodological gaps + missing canonical calculations in the terminal's pooled scanner:
  METHODOLOGICAL
    1. cross-sectional / within-name standardization before pooling     -> standardize, pool_standardized
    2. HAC (Newey-West) inference for OVERLAPPING forward returns        -> nw_mean_t, hac_slope (n_eff)
    3. transaction costs + turnover in backtests                        -> backtest_net (breakeven cost)
    4. confidence intervals on pooled means                            -> mean_ci, block_bootstrap_ci, diff_mean_ci
  CANONICAL
    5. cross-sectional rank-IC time series + NW t + fundamental-law IR  -> rank_ic_series, ic_summary
    6. long-short quantile portfolio + monotonicity                    -> quantile_ls
    7. regime-conditioned edge                                         -> regime_edge
    8. correlation: Ledoit-Wolf shrinkage + EWMA + significance        -> ledoit_wolf_constant_corr, ewma_corr, corr_pvalue
    9. Fama-MacBeth cross-sectional regression (risk premia)           -> fama_macbeth

Every estimator is unit-tested against planted structure in test_pooled_research.py.
"""
import math, random

# ----------------------------------------------------------------- basic stats
def _mean(x): return sum(x)/len(x) if x else 0.0
def _std(x, ddof=1):
    n=len(x)
    if n<=ddof: return 0.0
    m=_mean(x); return (sum((v-m)**2 for v in x)/(n-ddof))**0.5
def _rank(x):
    n=len(x); idx=sorted(range(n), key=lambda i:x[i]); r=[0.0]*n; i=0
    while i<n:
        j=i
        while j+1<n and x[idx[j+1]]==x[idx[i]]: j+=1
        avg=(i+j)/2.0+1.0
        for k in range(i,j+1): r[idx[k]]=avg
        i=j+1
    return r
def _pearson(x,y):
    n=min(len(x),len(y))
    if n<3: return 0.0
    x=x[:n]; y=y[:n]; mx=_mean(x); my=_mean(y)
    sxy=sum((x[i]-mx)*(y[i]-my) for i in range(n))
    sxx=sum((x[i]-mx)**2 for i in range(n)); syy=sum((y[i]-my)**2 for i in range(n))
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else 0.0
def _spearman(x,y):
    n=min(len(x),len(y))
    if n<3: return 0.0
    return _pearson(_rank(x[:n]), _rank(y[:n]))
def _ncdf(z): return 0.5*(1+math.erf(z/math.sqrt(2)))
def _nppf(p):
    if p<=0: return -1e9
    if p>=1: return 1e9
    a=[-3.969683028665376e+01,2.209460984245205e+02,-2.759285104469687e+02,1.383577518672690e+02,-3.066479806614716e+01,2.506628277459239e+00]
    b=[-5.447609879822406e+01,1.615858368580409e+02,-1.556989798598866e+02,6.680131188771972e+01,-1.328068155288572e+01]
    c=[-7.784894002430293e-03,-3.223964580411365e-01,-2.400758277161838e+00,-2.549732539343734e+00,4.374664141464968e+00,2.938163982698783e+00]
    d=[7.784695709041462e-03,3.224671290700398e-01,2.445134137142996e+00,3.754408661907416e+00]
    pl=0.02425
    if p<pl:
        q=math.sqrt(-2*math.log(p)); return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p<=1-pl:
        q=p-0.5; r=q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q=math.sqrt(-2*math.log(1-p)); return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)

# ------------------------------------------------ GAP 1: standardization before pooling
def standardize(x, method="z"):
    n=len(x)
    if n<2: return [0.0]*n
    if method=="rank":
        r=_rank(x); return [2*(ri-1)/(n-1)-1 for ri in r]
    m=_mean(x); s=_std(x)
    return [(v-m)/s for v in x] if s>0 else [0.0]*n
def pool_standardized(groups, method="z"):
    """groups: list of (sig, ret) per name. Standardize BOTH within each name, then pool -> (pooled_sig, pooled_ret).
    Removes the scale-mixing where loud (high-vol) names dominate a naive pooled correlation."""
    ps=[]; pr=[]
    for sig,ret in groups:
        n=min(len(sig),len(ret))
        if n<3: continue
        ps+=standardize(sig[:n],method); pr+=standardize(ret[:n],method)
    return ps,pr

# ------------------------------------------------ GAP 2: HAC / Newey-West (overlap)
def newey_west_lrv(u, maxlags):
    n=len(u); m=_mean(u); e=[v-m for v in u]
    s=sum(v*v for v in e)/n
    for L in range(1,maxlags+1):
        gl=sum(e[t]*e[t-L] for t in range(L,n))/n
        s+=2*(1-L/(maxlags+1))*gl
    return s
def nw_mean_t(u, maxlags=None):
    n=len(u)
    if n<3: return {"mean":_mean(u),"se":0.0,"t":0.0,"p":1.0,"n":n}
    if maxlags is None: maxlags=max(1,int(round(n**0.25)))
    lrv=newey_west_lrv(u,maxlags); se=math.sqrt(max(lrv,0)/n)
    m=_mean(u); t=m/se if se>0 else 0.0
    return {"mean":m,"se":se,"t":t,"p":2*(1-_ncdf(abs(t))),"n":n,"maxlags":maxlags}
def hac_slope(x,y,maxlags=None):
    """OLS slope of y on x with Newey-West HAC se. For H-day OVERLAPPING forward returns pass maxlags=H-1
    so the autocorrelation from overlap is not mistaken for signal. Reports n_eff = n/(maxlags+1)."""
    n=min(len(x),len(y))
    if n<5: return None
    x=x[:n]; y=y[:n]; mx=_mean(x); my=_mean(y); xc=[xi-mx for xi in x]
    sxx=sum(v*v for v in xc)
    if sxx<=0: return None
    b=sum(xc[i]*(y[i]-my) for i in range(n))/sxx; a=my-b*mx
    resid=[y[i]-(a+b*x[i]) for i in range(n)]
    if maxlags is None: maxlags=max(1,int(round(n**0.25)))
    g=[xc[i]*resid[i] for i in range(n)]; S=sum(v*v for v in g)
    for L in range(1,maxlags+1):
        S+=2*(1-L/(maxlags+1))*sum(g[t]*g[t-L] for t in range(L,n))
    var_b=S/(sxx*sxx); se=math.sqrt(max(var_b,0)); t=b/se if se>0 else 0.0
    return {"slope":b,"se":se,"t":t,"p":2*(1-_ncdf(abs(t))),"n":n,"n_eff":n/(maxlags+1),"r":_pearson(x,y),"maxlags":maxlags}

# ------------------------------------------------ GAP 3: costs + turnover
def backtest_net(positions, returns, cost_bps=5.0):
    n=min(len(positions),len(returns)); c=cost_bps/1e4
    gross=[]; net=[]; dps=[]; prev=0.0
    for i in range(n):
        dp=abs(positions[i]-prev); dps.append(dp); prev=positions[i]
        g=positions[i]*returns[i]; gross.append(g); net.append(g-c*dp)
    def shp(arr):
        s=_std(arr,0); return (_mean(arr)/s*math.sqrt(252)) if s>0 else 0.0
    mdp=_mean(dps); be=(_mean(gross)/mdp) if mdp>0 else None
    return {"grossSharpe":shp(gross),"netSharpe":shp(net),"turnover":mdp,
            "grossMean":_mean(gross),"netMean":_mean(net),
            "breakevenCost_bps":(be*1e4 if be is not None else None),"n":n}

# ------------------------------------------------ GAP 4: CIs on pooled means
def mean_ci(x, alpha=0.05):
    n=len(x)
    if n<2: return {"mean":_mean(x),"se":0.0,"lo":None,"hi":None,"n":n}
    m=_mean(x); se=_std(x)/math.sqrt(n); z=_nppf(1-alpha/2)
    return {"mean":m,"se":se,"lo":m-z*se,"hi":m+z*se,"n":n}
def block_bootstrap_ci(x, alpha=0.05, block=5, B=2000, seed=12345):
    n=len(x)
    if n<5: return {"mean":_mean(x),"lo":None,"hi":None}
    rng=random.Random(seed); means=[]
    for _ in range(B):
        samp=[]
        while len(samp)<n:
            st=rng.randrange(0,n)
            for k in range(block): samp.append(x[(st+k)%n])
        means.append(_mean(samp[:n]))
    means.sort()
    return {"mean":_mean(x),"lo":means[int((alpha/2)*B)],"hi":means[int((1-alpha/2)*B)],"B":B,"block":block}
def diff_mean_ci(a,b,alpha=0.05):
    na,nb=len(a),len(b); m=_mean(a)-_mean(b)
    se=math.sqrt((_std(a)**2/na if na>1 else 0)+(_std(b)**2/nb if nb>1 else 0)); z=_nppf(1-alpha/2)
    return {"diff":m,"se":se,"lo":m-z*se,"hi":m+z*se,"na":na,"nb":nb}

# ------------------------------------------------ CANONICAL 5: rank-IC + breadth/IR
def rank_ic_series(panel_sig, panel_fwd, min_names=5):
    ics=[]; breadth=[]
    for sig,fwd in zip(panel_sig,panel_fwd):
        names=[k for k in sig if k in fwd and sig[k]==sig[k] and fwd[k]==fwd[k]]
        if len(names)<min_names: continue
        ics.append(_spearman([sig[k] for k in names],[fwd[k] for k in names])); breadth.append(len(names))
    return ics,breadth
def ic_summary(ics, breadth=None, maxlags=None):
    if len(ics)<3: return None
    nw=nw_mean_t(ics,maxlags); sd=_std(ics)
    bavg=_mean(breadth) if breadth else 0
    return {"meanIC":nw["mean"],"icT":nw["t"],"icP":nw["p"],"hitRate":sum(1 for v in ics if v>0)/len(ics),
            "IR_periodic":(_mean(ics)/sd if sd>0 else 0.0),"breadth":bavg,
            "IR_law":(_mean(ics)*math.sqrt(bavg) if bavg>0 else None),"nDates":len(ics)}

# ------------------------------------------------ CANONICAL 6: long-short quantile + monotonicity
def quantile_ls(panel_sig, panel_fwd, q=5):
    bucket=[[] for _ in range(q)]; ls=[]
    for sig,fwd in zip(panel_sig,panel_fwd):
        names=[k for k in sig if k in fwd]
        if len(names)<q: continue
        order=sorted(names,key=lambda k:sig[k]); m=len(order); per=m/q; bmeans=[]
        for bi in range(q):
            lo=int(round(bi*per)); hi=int(round((bi+1)*per)) if bi<q-1 else m; grp=order[lo:hi]
            if not grp: bmeans.append(None); continue
            r=_mean([fwd[k] for k in grp]); bmeans.append(r); bucket[bi].append(r)
        if bmeans[0] is not None and bmeans[-1] is not None: ls.append(bmeans[-1]-bmeans[0])
    bavg=[_mean(bk) if bk else None for bk in bucket]
    idx=[i for i,bk in enumerate(bavg) if bk is not None]; vals=[bavg[i] for i in idx]
    mono=_spearman([float(i) for i in idx],vals) if len(idx)>=3 else 0.0
    nw=nw_mean_t(ls) if len(ls)>=3 else None
    sh=(_mean(ls)/_std(ls)*math.sqrt(252)) if ls and _std(ls)>0 else 0.0
    return {"bucketMeans":bavg,"monotonicity":mono,"lsMean":(_mean(ls) if ls else 0.0),
            "lsT":(nw["t"] if nw else 0.0),"lsP":(nw["p"] if nw else 1.0),"lsSharpe":sh,"nDates":len(ls),"q":q}

# ------------------------------------------------ CANONICAL 7: regime-conditioned edge
def regime_edge(sig, fwd, regime, thr=0.0):
    out={}
    for lab in sorted(set(regime)):
        xs=[sig[i] for i in range(len(sig)) if regime[i]==lab]
        ys=[fwd[i] for i in range(len(fwd)) if regime[i]==lab]
        if len(xs)<5: out[lab]=None; continue
        up=[ys[i] for i in range(len(xs)) if xs[i]>thr]
        out[lab]={"ic":_spearman(xs,ys),"meanFwdLong":(_mean(up) if up else None),"n":len(xs)}
    labs=[l for l in out if out[l]]
    diff=(out[labs[0]]["ic"]-out[labs[-1]]["ic"]) if len(labs)>=2 else None
    return {"byRegime":out,"icSpread":diff}

# ------------------------------------------------ CANONICAL 8: correlation shrinkage / EWMA / sig
def sample_corr(rets):
    names=[k for k in rets if len(rets[k])>=5]
    if len(names)<2: return names,[]
    n=min(len(rets[k]) for k in names); R={k:rets[k][-n:] for k in names}
    return names,[[_pearson(R[a],R[b]) for b in names] for a in names]
def ledoit_wolf_constant_corr(rets):
    names,C=sample_corr(rets); p=len(names)
    if p<2: return names,C,0.0
    off=[C[i][j] for i in range(p) for j in range(p) if i!=j]
    rbar=_mean(off); n=min(len(rets[k]) for k in names)
    pi=_mean([(c-rbar)**2 for c in off])                 # dispersion of sample corrs around target
    rho_=_mean([((1-c*c)**2)/n for c in off])            # ~ avg sampling variance of a correlation
    delta=max(0.0,min(1.0,(rho_/(pi+rho_)) if (pi+rho_)>0 else 1.0))
    S=[[(1.0 if i==j else (1-delta)*C[i][j]+delta*rbar) for j in range(p)] for i in range(p)]
    return names,S,delta
def ewma_corr(rets, lam=0.94):
    names=[k for k in rets if len(rets[k])>=5]
    if len(names)<2: return names,[]
    n=min(len(rets[k]) for k in names); R={k:rets[k][-n:] for k in names}
    w=[(1-lam)*lam**(n-1-t) for t in range(n)]; sw=sum(w); w=[wi/sw for wi in w]
    mu={k:sum(w[t]*R[k][t] for t in range(n)) for k in names}
    def cov(a,b): return sum(w[t]*(R[a][t]-mu[a])*(R[b][t]-mu[b]) for t in range(n))
    var={k:cov(k,k) for k in names}
    return names,[[(cov(a,b)/math.sqrt(var[a]*var[b]) if var[a]>0 and var[b]>0 else 0.0) for b in names] for a in names]
def corr_pvalue(r,n):
    if n<4 or abs(r)>=1: return 0.0 if abs(r)>=1 else 1.0
    t=r*math.sqrt((n-2)/(1-r*r)); return 2*(1-_ncdf(abs(t)))

# ------------------------------------------------ CANONICAL 9: Fama-MacBeth
def _solve(A,b):
    n=len(A); M=[A[i][:]+[b[i]] for i in range(n)]
    for c in range(n):
        piv=max(range(c,n),key=lambda r:abs(M[r][c]))
        if abs(M[piv][c])<1e-12: return None
        M[c],M[piv]=M[piv],M[c]
        for r in range(n):
            if r!=c:
                f=M[r][c]/M[c][c]
                for k in range(c,n+1): M[r][k]-=f*M[c][k]
    return [M[i][n]/M[i][i] for i in range(n)]
def _ols(rows,y):
    n=len(rows); k=len(rows[0]); X=[[1.0]+list(r) for r in rows]; p=k+1
    XtX=[[sum(X[t][i]*X[t][j] for t in range(n)) for j in range(p)] for i in range(p)]
    Xty=[sum(X[t][i]*y[t] for t in range(n)) for i in range(p)]
    return _solve(XtX,Xty)
def fama_macbeth(panel_X, panel_y, maxlags=None):
    """panel_X: list of cross-sections name->[factor values]; panel_y: list name->fwd return.
    Per-date cross-sectional OLS y~X; FM risk premia = NW mean of slope series. Returns per-factor coef + t."""
    slopes=[]
    for X,y in zip(panel_X,panel_y):
        names=[k for k in X if k in y]
        if len(names)<3: continue
        b=_ols([X[k] for k in names],[y[k] for k in names])
        if b is not None: slopes.append(b)
    if len(slopes)<3: return None
    kf=len(slopes[0]); out=[]
    for j in range(kf):
        nw=nw_mean_t([s[j] for s in slopes],maxlags)
        out.append({"coef":nw["mean"],"t":nw["t"],"p":nw["p"]})
    return {"intercept":out[0],"lambdas":out[1:],"nDates":len(slopes)}
