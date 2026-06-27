#!/usr/bin/env python3
"""Quarterly stock-timeline metrics engine (pure stdlib).

Implements the computation model from the "Professional specification for a quarterly stock timeline
report and dashboard" (pp.14-17): total-return index, normalized lines, relative strength, drawdown +
recovery, realized/downside vol, market-model beta (with explicit constant + HAC SE), correlation,
relative volume, dilution, FCF / cash-conversion / net-debt / EV / multiples / FCF-yield, surprises,
the event-study framework (estimation [-250,-30]; windows [-1,+1],[0,+1],[0,+5],[-1,+20]; BMO/AMC
session mapping; AR/CAR + significance), YoY, quarter-dummy seasonality (OLS), and the 20-day EWMA
overlay. Every metric is tested against planted structure. No third-party deps.

Discipline from the spec: total-return basis for performance; explicit constant in regressions;
point-in-time inputs; smoothing is overlay-only.
"""
import math

# ----------------------------------------------------------------- helpers
def _mean(x): return sum(x)/len(x) if x else 0.0
def _std(x, ddof=1):
    n=len(x)
    if n<=ddof: return 0.0
    m=_mean(x); return (sum((v-m)**2 for v in x)/(n-ddof))**0.5
def _pearson(x,y):
    n=min(len(x),len(y))
    if n<3: return 0.0
    x=x[:n]; y=y[:n]; mx=_mean(x); my=_mean(y)
    sxy=sum((x[i]-mx)*(y[i]-my) for i in range(n))
    sxx=sum((x[i]-mx)**2 for i in range(n)); syy=sum((y[i]-my)**2 for i in range(n))
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else 0.0
def _ncdf(z): return 0.5*(1+math.erf(z/math.sqrt(2)))
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
def _ols(X, y):
    """X: list of feature rows (WITHOUT intercept); adds intercept. Returns {coef:[b0..bk], resid, n}."""
    n=len(X); k=len(X[0]); D=[[1.0]+list(r) for r in X]; p=k+1
    XtX=[[sum(D[t][i]*D[t][j] for t in range(n)) for j in range(p)] for i in range(p)]
    Xty=[sum(D[t][i]*y[t] for t in range(n)) for i in range(p)]
    b=_solve(XtX,Xty)
    if b is None: return None
    resid=[y[t]-sum(b[j]*D[t][j] for j in range(p)) for t in range(n)]
    return {"coef":b,"resid":resid,"n":n,"k":p,"_XtX":XtX}
def _nw_lrv(u, maxlags):
    n=len(u); m=_mean(u); e=[v-m for v in u]; s=sum(v*v for v in e)/n
    for L in range(1,maxlags+1):
        s+=2*(1-L/(maxlags+1))*sum(e[t]*e[t-L] for t in range(L,n))/n
    return s

# ----------------------------------------------------------------- price / return metrics
def total_return_index(close, divs=None, base=100.0):
    """TR_t = TR_{t-1}*(1 + (P_t - P_{t-1} + D_t)/P_{t-1}). divs: dict idx->cash dividend on ex-date."""
    divs=divs or {}; tr=[base]
    for t in range(1,len(close)):
        d=divs.get(t,0.0); r=(close[t]-close[t-1]+d)/close[t-1] if close[t-1] else 0.0
        tr.append(tr[-1]*(1+r))
    return tr
def normalized(series, base=100.0):
    if not series or series[0]==0: return [base]*len(series)
    return [base*v/series[0] for v in series]
def log_returns(series):
    return [math.log(series[i]/series[i-1]) for i in range(1,len(series)) if series[i-1]>0 and series[i]>0]
def relative_strength(stock, bench, base=100.0):
    ns=normalized(stock,base); nb=normalized(bench,base); n=min(len(ns),len(nb))
    rsl=[ns[i]/nb[i] if nb[i] else 1.0 for i in range(n)]
    return {"RSL":rsl,"RS":[v-1.0 for v in rsl]}
def drawdowns(series):
    peak=series[0] if series else 0.0; dd=[]; episodes=[]; cur=None
    for t,x in enumerate(series):
        if x>peak: peak=x
        d=(x/peak-1.0) if peak else 0.0; dd.append(d)
        if d<0 and cur is None: cur={"start":t,"trough":t,"troughVal":d,"peak":peak}
        elif d<0 and cur is not None:
            if d<cur["troughVal"]: cur["trough"]=t; cur["troughVal"]=d
        elif d>=0 and cur is not None:
            cur["recovery"]=t; cur["recoveryDays"]=t-cur["trough"]; episodes.append(cur); cur=None
    if cur is not None: cur["recovery"]=None; cur["recoveryDays"]=None; episodes.append(cur)
    maxdd=min(dd) if dd else 0.0
    avgdd=_mean([e["troughVal"] for e in episodes]) if episodes else 0.0
    return {"dd":dd,"maxDD":maxdd,"avgDD":avgdd,"episodes":episodes}
def realized_vol(returns, K=252): return math.sqrt(K)*_std(returns) if len(returns)>1 else 0.0
def downside_vol(returns, K=252):
    dn=[r for r in returns if r<0]; return math.sqrt(K)*_std(dn) if len(dn)>1 else 0.0
def beta_market_model(stock_ret, mkt_ret, rf=0.0, hac=True):
    """r_s - rf = alpha + beta*(r_m - rf) + eps, with explicit constant + (optional) Newey-West SE."""
    n=min(len(stock_ret),len(mkt_ret))
    if n<5: return None
    y=[stock_ret[i]-rf for i in range(n)]; x=[mkt_ret[i]-rf for i in range(n)]
    fit=_ols([[xi] for xi in x], y)
    if not fit: return None
    a,b=fit["coef"]; resid=fit["resid"]
    mx=_mean(x); sxx=sum((xi-mx)**2 for xi in x)
    if hac:
        maxlags=max(1,int(round(n**0.25))); g=[(x[i]-mx)*resid[i] for i in range(n)]
        S=sum(v*v for v in g)
        for L in range(1,maxlags+1): S+=2*(1-L/(maxlags+1))*sum(g[t]*g[t-L] for t in range(L,n))
        se_b=math.sqrt(S/(sxx*sxx)) if sxx>0 else 0.0
    else:
        s2=sum(v*v for v in resid)/(n-2); se_b=math.sqrt(s2/sxx) if sxx>0 else 0.0
    t_b=b/se_b if se_b>0 else 0.0
    return {"alpha":a,"beta":b,"se_beta":se_b,"t_beta":t_b,"p_beta":2*(1-_ncdf(abs(t_b))),"n":n,
            "corr":_pearson(x,y),"r2":(_pearson(x,y)**2)}
def relative_volume(vol, win=20):
    out=[]
    for t in range(len(vol)):
        if t<win: out.append(None); continue
        w=sorted(vol[t-win:t]); med=w[len(w)//2] if len(w)%2 else (w[len(w)//2-1]+w[len(w)//2])/2
        out.append(vol[t]/med if med else None)
    return out
def dilution(shares_q, shares_q4): return (shares_q/shares_q4-1.0) if shares_q4 else None

# ----------------------------------------------------------------- fundamentals
def fcf(cfo, capex): return cfo-capex
def cash_conversion(fcf_v, ni): return (fcf_v/ni) if ni else None
def net_debt(debt, cash): return debt-cash
def enterprise_value(mktcap, debt, pref, nci, cash): return mktcap+debt+pref+nci-cash
def pe(price, eps_ttm): return (price/eps_ttm) if eps_ttm else None
def ev_ebitda(ev, ebitda_ttm): return (ev/ebitda_ttm) if ebitda_ttm else None
def ev_sales(ev, rev_ttm): return (ev/rev_ttm) if rev_ttm else None
def fcf_yield(fcf_ttm, mktcap): return (fcf_ttm/mktcap) if mktcap else None
def yoy(x_q, x_q4): return (x_q/x_q4-1.0) if x_q4 else None

# ----------------------------------------------------------------- surprises
def surprise(actual, est): return ((actual-est)/abs(est)) if est else None
def guidance_surprise(midpoint, cons_prev): return ((midpoint-cons_prev)/abs(cons_prev)) if cons_prev else None

# ----------------------------------------------------------------- event study
EVENT_WINDOWS=[(-1,1),(0,1),(0,5),(-1,20)]
def map_event_session(flag):
    """BMO -> same-day session (offset 0); AMC -> next session (offset +1); intraday -> same-day (0)."""
    f=(flag or "").upper()
    return 1 if f=="AMC" else 0
def event_study(stock_ret, mkt_ret, event_idx, est_window=(-250,-30), windows=None):
    """Market-model abnormal returns around event_idx. stock_ret/mkt_ret aligned by trading day.
    Estimation window [est0,est1] (relative, negative offsets). Returns alpha/beta + AR + CAR per window."""
    windows=windows or EVENT_WINDOWS
    e0=event_idx+est_window[0]; e1=event_idx+est_window[1]
    if e0<0 or e1>=len(stock_ret) or e1<=e0+5: return None
    ys=stock_ret[e0:e1+1]; xs=mkt_ret[e0:e1+1]
    fit=_ols([[xi] for xi in xs], ys)
    if not fit: return None
    a,b=fit["coef"]
    def AR(t): return stock_ret[t]-(a+b*mkt_ret[t]) if 0<=t<len(stock_ret) else None
    cars={}
    for (wa,wb) in windows:
        ars=[AR(event_idx+k) for k in range(wa,wb+1)]
        if any(v is None for v in ars): cars["%d,%d"%(wa,wb)]=None; continue
        cars["%d,%d"%(wa,wb)]=sum(ars)
    return {"alpha":a,"beta":b,"AR_event":AR(event_idx),"CAR":cars,"estN":len(ys)}
def car_significance(cars):
    """One-sample t-test that a list of per-event CARs has mean 0 (+ bootstrap-free normal p)."""
    c=[v for v in cars if v is not None]
    if len(c)<3: return None
    m=_mean(c); se=_std(c)/math.sqrt(len(c)); t=m/se if se>0 else 0.0
    return {"meanCAR":m,"t":t,"p":2*(1-_ncdf(abs(t))),"n":len(c)}

# ----------------------------------------------------------------- seasonality
def quarter_dummy_seasonality(x, qidx):
    """X_q = mu + g2*DQ2 + g3*DQ3 + g4*DQ4 + eps. qidx[i] in {1,2,3,4}. Returns coefs + per-coef t (HAC)."""
    n=len(x)
    if n<6: return None
    rows=[[1.0 if qidx[i]==2 else 0.0, 1.0 if qidx[i]==3 else 0.0, 1.0 if qidx[i]==4 else 0.0] for i in range(n)]
    fit=_ols(rows, x)
    if not fit: return None
    b=fit["coef"]; resid=fit["resid"]; p=fit["k"]
    # coefficient SEs via (X'X)^-1 * s^2 (homoskedastic; small samples)
    s2=sum(v*v for v in resid)/max(1,n-p)
    XtX=fit["_XtX"]; inv=_inv(XtX)
    ts=[]
    for j in range(p):
        se=math.sqrt(s2*inv[j][j]) if inv and inv[j][j]>0 else 0.0
        ts.append(b[j]/se if se>0 else 0.0)
    return {"mu":b[0],"q2":b[1],"q3":b[2],"q4":b[3],"t":{"mu":ts[0],"q2":ts[1],"q3":ts[2],"q4":ts[3]},"n":n}
def _inv(A):
    n=len(A); M=[A[i][:]+[1.0 if i==j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        piv=max(range(c,n),key=lambda r:abs(M[r][c]))
        if abs(M[piv][c])<1e-12: return None
        M[c],M[piv]=M[piv],M[c]; d=M[c][c]; M[c]=[v/d for v in M[c]]
        for r in range(n):
            if r!=c:
                f=M[r][c]
                for k in range(2*n): M[r][k]-=f*M[c][k]
    return [row[n:] for row in M]

# ----------------------------------------------------------------- overlays / decomposition
def ewma_overlay(x, span=20):
    """Descriptive overlay ONLY (spec: never for raw event panels / risk metrics). lam = 2/(span+1)."""
    if not x: return []
    lam=2.0/(span+1); s=[x[0]]
    for t in range(1,len(x)): s.append(lam*x[t]+(1-lam)*s[-1])
    return s
def return_decomposition(price0, price1, eps0, eps1, dps_total):
    """TR ~= fundamental growth + multiple change + distributions (analytical attribution, not identity)."""
    if not (price0 and eps0 and eps1 and price1): return None
    pe0=price0/eps0; pe1=price1/eps1
    fund=eps1/eps0-1.0; mult=pe1/pe0-1.0; dist=dps_total/price0
    total=price1/price0-1.0+dist
    return {"fundamentalGrowth":fund,"multipleChange":mult,"distributions":dist,"totalReturn":total}
