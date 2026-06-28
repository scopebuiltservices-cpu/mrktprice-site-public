#!/usr/bin/env python3
"""MrktPrice Market Map — daily cross-sectional precompute for the index universes.

Computes, per constituent, a coherent metric matrix and writes a compact snapshot the
marketmap.html page renders (scatter / treemap / correlation / sector-factor grid).

Metrics: returns (1w..12m), annualized vol, market beta, Fama-French OLS loadings,
FREE CASH FLOW + FCF yield (EDGAR CFO-CapEx), DAILY MONEY FLOW (signed price*volume ->
inflow/outflow, net ratio over 1m/3m), winsorized cross-sectional z-scores, and a
PCA-clustered sector return-correlation matrix.

Modes:
  --demo   coherent SYNTHETIC seed (no network) so the UI works immediately
  --real   fetch real constituents (index ETF holdings), prices+volume (yfinance/Stooq),
           and FCF (SEC EDGAR XBRL) — used by the nightly GitHub Action
Output: ../../marketmap.json

Stdlib-only math (self-tested); --real adds yfinance/requests. Research only; not advice.
"""
from __future__ import annotations
import argparse, json, math, os, random, re, sys, time, datetime as dt
import xml.etree.ElementTree as ET
try:
    import lineage as _lineage   # Phase 2 regime-lineage engine (same dir)
except Exception:
    _lineage=None
try:
    import options_gex as _ogex, eodhd_options as _eod, fmp_connector as _fmp, short_squeeze as _sqz, alpaca_options as _alp, est_snapshot as _es
except Exception:
    _ogex=_eod=_fmp=_sqz=_alp=_es=None

SECTORS=["Technology","Financials","Health Care","Consumer Disc.","Communication",
         "Industrials","Consumer Staples","Energy","Utilities","Materials","Real Estate"]
FACTORS=["MKT","SMB","HML","MOM"]

# ---------- pure metric math (unit-tested) ----------------------------------------------------
def winsorize(xs,p=0.02):
    ys=sorted(v for v in xs if v is not None and v==v)
    if not ys: return list(xs)
    lo=ys[max(0,int(p*len(ys)))]; hi=ys[min(len(ys)-1,int((1-p)*len(ys)))]
    return [None if (v is None or v!=v) else min(max(v,lo),hi) for v in xs]

def zscores(xs):
    vals=[v for v in xs if v is not None and v==v]
    if len(vals)<2: return [0.0 for _ in xs]
    m=sum(vals)/len(vals); sd=(sum((v-m)**2 for v in vals)/(len(vals)-1))**0.5 or 1.0
    return [0.0 if (v is None or v!=v) else (v-m)/sd for v in xs]

def ann_vol(w):
    r=[x for x in w if x==x]
    if len(r)<3: return float("nan")
    mu=sum(r)/len(r); return (sum((x-mu)**2 for x in r)/(len(r)-1))**0.5*math.sqrt(52)

def beta(a,m):
    pr=[(x,y) for x,y in zip(a,m) if x==x and y==y]; n=len(pr)
    if n<5: return float("nan")
    ma=sum(x for x,_ in pr)/n; mm=sum(y for _,y in pr)/n
    cov=sum((x-ma)*(y-mm) for x,y in pr)/(n-1); var=sum((y-mm)**2 for _,y in pr)/(n-1)
    return cov/var if var>0 else float("nan")

def pearson(a,b):
    pr=[(x,y) for x,y in zip(a,b) if x==x and y==y]; n=len(pr)
    if n<3: return float("nan")
    ma=sum(x for x,_ in pr)/n; mb=sum(y for _,y in pr)/n
    sa=(sum((x-ma)**2 for x,_ in pr))**0.5; sb=(sum((y-mb)**2 for _,y in pr))**0.5
    return sum((x-ma)*(y-mb) for x,y in pr)/(sa*sb) if sa and sb else float("nan")

def _var(a):
    v=[x for x in a if x==x]
    if len(v)<2: return 0.0
    m=sum(v)/len(v); return sum((x-m)**2 for x in v)/(len(v)-1)

def _resid_on(a,c):                       # residual of a regressed on single control c (for partial corr)
    b=beta(a,c)
    if b!=b: return list(a)
    ma=sum(a)/len(a); mc=sum(c)/len(c)
    return [a[i]-(ma+b*(c[i]-mc)) for i in range(len(a))]

def partial_corr(y,x,ctrl):               # correlation of y,x after removing the linear effect of ctrl
    return pearson(_resid_on(y,ctrl),_resid_on(x,ctrl))

# ---- Student-t two-sided p (exact, via regularized incomplete beta) — replaces the normal approx so
#      small-sample (n~53 weekly) correlation significance is honest; feeds the FDR control below. ----
def _betacf(a,b,x,itmax=200,eps=3e-12):
    qab=a+b; qap=a+1.0; qam=a-1.0; c=1.0; d=1.0-qab*x/qap
    d=1e-30 if abs(d)<1e-30 else d; d=1.0/d; h=d
    for m in range(1,itmax+1):
        m2=2*m
        aa=m*(b-m)*x/((qam+m2)*(a+m2))
        d=1.0+aa*d; d=1e-30 if abs(d)<1e-30 else d
        c=1.0+aa/c; c=1e-30 if abs(c)<1e-30 else c
        d=1.0/d; h*=d*c
        aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2))
        d=1.0+aa*d; d=1e-30 if abs(d)<1e-30 else d
        c=1.0+aa/c; c=1e-30 if abs(c)<1e-30 else c
        d=1.0/d; de=d*c; h*=de
        if abs(de-1.0)<eps: break
    return h
def _betai(a,b,x):                        # regularized incomplete beta I_x(a,b)
    if x<=0.0: return 0.0
    if x>=1.0: return 1.0
    bt=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log(1.0-x))
    return bt*_betacf(a,b,x)/a if x<(a+1.0)/(a+b+2.0) else 1.0-bt*_betacf(b,a,1.0-x)/b
def _t_two_sided_p(t,df):                 # P(|T_df| > |t|); ν=df>0
    t=abs(t)
    if df<=0 or t!=t: return 1.0
    if t>1e6: return 0.0
    return _betai(df/2.0, 0.5, df/(df+t*t))

def ols_betas(y,X):
    k=len(X[0]); n=len(y)
    XtX=[[sum(X[r][i]*X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    Xty=[sum(X[r][i]*y[r] for r in range(n)) for i in range(k)]
    A=[row[:]+[Xty[i]] for i,row in enumerate(XtX)]
    for c in range(k):
        piv=max(range(c,k),key=lambda r:abs(A[r][c]))
        if abs(A[piv][c])<1e-12: return [0.0]*k
        A[c],A[piv]=A[piv],A[c]; d=A[c][c]; A[c]=[v/d for v in A[c]]
        for r in range(k):
            if r!=c:
                f=A[r][c]; A[r]=[A[r][j]-f*A[c][j] for j in range(k+1)]
    return [A[i][k] for i in range(k)]

def cluster_order(M):
    n=len(M)
    if n==0: return []
    v=[1.0/math.sqrt(n)]*n
    for _ in range(60):
        w=[sum(M[i][j]*v[j] for j in range(n)) for i in range(n)]
        nrm=math.sqrt(sum(x*x for x in w)) or 1.0; v=[x/nrm for x in w]
    return sorted(range(n),key=lambda i:v[i])

def money_flow(closes, vols):
    """Daily money flow: dollar volume signed by the day's return.
    Returns (net_ratio, inflow$, outflow$, last_in$, last_out$) over the supplied window.
    Inflow = up-day $volume, Outflow = down-day $volume; net = (in-out)/(in+out) in [-1,1]."""
    infl=outfl=0.0; last_in=last_out=0.0
    for i in range(1,len(closes)):
        c0,c1,v=closes[i-1],closes[i],vols[i]
        if c0 is None or c1 is None or v is None: continue
        if c0!=c0 or c1!=c1 or v!=v: continue            # skip NaN bars (yfinance gaps)
        dv=c1*v; r=c1-c0
        if r>=0: infl+=dv; last_in=dv; last_out=0.0
        else: outfl+=dv; last_out=dv; last_in=0.0
    tot=infl+outfl
    net=(infl-outfl)/tot if tot>0 else float("nan")
    return net, infl, outfl, last_in, last_out

# ---------- analytics added from cash-flow analysis review (all pure-python, unit-tested) ------
MACROF=["MKT","DXY","RATE","VIX","OIL"]   # macro factor panel for the sparse attribution

def _ok(*xs):
    for x in xs:
        if x is None or x!=x: return False
    return True

def mfi(highs, lows, closes, vols, period=14):
    """Money Flow Index (0..100): bounded money-flow oscillator on typical price.
    TP=(H+L+C)/3; RMF=TP*Vol; up-day RMF is positive flow, down-day negative; MFI=100-100/(1+pos/neg)."""
    tp=[((h+l+c)/3.0 if _ok(h,l,c) else None) for h,l,c in zip(highs,lows,closes)]
    flows=[]
    for i in range(1,len(tp)):
        if tp[i] is None or tp[i-1] is None or not _ok(vols[i]): continue
        rmf=tp[i]*vols[i]
        if tp[i]>tp[i-1]: flows.append((rmf,0.0))
        elif tp[i]<tp[i-1]: flows.append((0.0,rmf))
        else: flows.append((0.0,0.0))
    flows=flows[-period:]
    pos=sum(f[0] for f in flows); neg=sum(f[1] for f in flows)
    if neg<=0: return 100.0 if pos>0 else 50.0
    return 100.0-100.0/(1.0+pos/neg)

def atr(highs, lows, closes, period=14):
    """Average True Range over `period` days (Wilder true range, simple mean)."""
    trs=[]
    for i in range(1,len(closes)):
        h,l,pc=highs[i],lows[i],closes[i-1]
        if not _ok(h,l,pc): continue
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    trs=trs[-period:]
    return sum(trs)/len(trs) if trs else float("nan")

def zstd(col):
    v=[x for x in col if _ok(x)]
    if len(v)<2: return [0.0 for _ in col],0.0,1.0
    m=sum(v)/len(v); sd=(sum((x-m)**2 for x in v)/len(v))**0.5 or 1.0
    return [((x-m)/sd if _ok(x) else 0.0) for x in col],m,sd

def lasso_cd(y, X, alpha=0.08, iters=300):
    """Lasso via coordinate descent on STANDARDIZED y and X (so betas are comparable,
    L1 penalises predictive power not raw scale). Returns sparse standardized betas.
    Objective: (1/2n)||y-Xb||^2 + lambda*||b||_1, lambda=alpha*n. Gram-matrix CD for speed."""
    n=len(y); k=len(X[0]) if (n and X) else 0
    if n<6 or k==0: return [0.0]*k
    ys,_,_=zstd(y)
    cols=[[X[r][j] for r in range(n)] for j in range(k)]
    Z=[zstd(c)[0] for c in cols]                       # standardized columns
    G=[[sum(Z[a][r]*Z[b][r] for r in range(n)) for b in range(k)] for a in range(k)]
    Zty=[sum(Z[a][r]*ys[r] for r in range(n)) for a in range(k)]
    lam=alpha*n; beta=[0.0]*k
    for _ in range(iters):
        for j in range(k):
            rho=Zty[j]-sum(G[j][t]*beta[t] for t in range(k))+G[j][j]*beta[j]
            d=G[j][j] or 1.0; z=rho/d; g=lam/d
            beta[j]= z-g if z>g else (z+g if z<-g else 0.0)
    return beta

def macro_fit(y, factors):
    """OLS fit of y on the macro factor columns (list of equal-length series); returns
    (fitted, residuals). Used for the dislocation residual after Lasso flags active drivers."""
    n=len(y); k=len(factors)
    if n<6 or k==0: return list(y),[0.0]*n
    X=[[1.0]+[factors[j][r] for j in range(k)] for r in range(n)]
    b=ols_betas(y,X)
    fit=[sum(X[r][c]*b[c] for c in range(k+1)) for r in range(n)]
    return fit,[y[r]-fit[r] for r in range(n)]

# ---- decision-path analytics from the Value-Prediction-Pipeline review (EMA21-first) ----
def ema_series(xs, span):
    a=2.0/(span+1.0); out=[]; e=None
    for x in xs:
        if x is None or x!=x: out.append(e); continue
        e=x if e is None else a*x+(1.0-a)*e; out.append(e)
    return out

def daily_logvol(closes):
    r=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))
       if _ok(closes[i],closes[i-1]) and closes[i]>0 and closes[i-1]>0]
    if len(r)<5: return float("nan")
    m=sum(r)/len(r); return (sum((x-m)**2 for x in r)/(len(r)-1))**0.5

def _logret(closes,n=None):
    r=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))
       if _ok(closes[i],closes[i-1]) and closes[i]>0 and closes[i-1]>0]
    return r[-n:] if n else r

def half_life(closes, cap=252):
    """P3-33 mean-reversion half-life (Ornstein-Uhlenbeck). Regress dp on prior log-price:
    dp_t = a + b*p_{t-1}; b<0 => mean-reverting, half-life = ln2/(-b) days. None if trending."""
    p=[math.log(c) for c in closes if _ok(c) and c>0]
    if len(p)<25: return None
    dp=[p[i]-p[i-1] for i in range(1,len(p))]; lag=p[:-1]
    b=beta(dp,lag)
    if b!=b or b>=0: return None                       # b>=0 => no reversion (trending/random walk)
    h=math.log(2)/(-b)
    return round(min(h,cap),1) if h>0 else None

def variance_ratio(closes, q=5):
    """P3-25 Lo-MacKinlay variance ratio. VR=Var(q-sum)/(q*Var(1)). >1 trending, <1 mean-reverting, ~1 random walk."""
    r=_logret(closes)
    if len(r)<q*4: return None
    v1=_var(r)
    if v1<=0: return None
    qs=[sum(r[i:i+q]) for i in range(0,len(r)-q+1)]
    vq=_var(qs)
    return round(vq/(q*v1),2) if v1>0 else None

def parkinson_vol(highs, lows, n=21):
    """P3-19 Parkinson range volatility (daily): sqrt( (1/(4 ln2 N)) * sum ln(H/L)^2 ). More efficient than close-to-close."""
    pr=[(h,l) for h,l in zip(highs[-n:],lows[-n:]) if _ok(h,l) and l>0 and h>=l]
    if len(pr)<5: return None
    s=sum(math.log(h/l)**2 for h,l in pr)
    return math.sqrt(s/(4.0*math.log(2)*len(pr)))      # daily sigma

def jump_ratio(closes, n=21):
    """P3-20 jump fraction from bipower variation. (RV-BV)/RV in [0,1]; high => recent discontinuous (event) moves."""
    r=_logret(closes,n)
    if len(r)<8: return None
    rv=sum(x*x for x in r)
    if rv<=0: return None
    mu1=math.sqrt(2.0/math.pi)
    bv=(mu1**-2)*sum(abs(r[i])*abs(r[i-1]) for i in range(1,len(r)))
    return round(max(0.0,min(1.0,(rv-bv)/rv)),2)

def _phi(x):  # standard-normal CDF
    return 0.5*(1.0+math.erf(x/math.sqrt(2.0)))

def prob_touch(S, B, sig_d, T):
    """Driftless first-passage probability that GBM started at S touches barrier B within T
    trading days, given daily log-vol sig_d. Reflection-principle approximation, clamped [0,1]."""
    if not (S>0 and B>0) or sig_d<=0 or T<=0: return 0.0
    s=sig_d*math.sqrt(T); d=abs(math.log(B/S))
    if s<=0: return 0.0
    return max(0.0,min(1.0,2.0*(1.0-_phi(d/s))))

def contradiction(signals):
    """P3-42 agreement: signals = list of (name, value, weight). Dominant direction s* = sign of
    the weighted sum of signs; agreement = (weight of signals matching s*)/(total weight).
    Returns (contradiction in [0,1] = 1-agreement, direction str, list of conflicting names)."""
    sig=[(nm,(1 if v>0 else (-1 if v<0 else 0)),w) for nm,v,w in signals if v==v]
    sig=[x for x in sig if x[1]!=0]
    if not sig: return 0.0,"flat",[]
    W=sum(w for _,_,w in sig); ws=sum(sg*w for _,sg,w in sig)
    star=1 if ws>0 else (-1 if ws<0 else 0)
    if star==0: return 1.0,"mixed",[nm for nm,_,_ in sig]
    agree=sum(w for _,sg,w in sig if sg==star)/W
    conf=[nm for nm,sg,_ in sig if sg!=star]
    return round(1.0-agree,2),("up" if star>0 else "down"),conf

_Q75=0.6744897501960817   # Phi^-1(0.75)
def median_touch_days(S, B, sigD, cap=252):
    """Median first-passage time (trading days) for driftless GBM from S to barrier B.
    From P(touch by t)=0.5 -> t = (ln|B/S|/(sigD*Phi^-1(.75)))^2."""
    if not (S>0 and B>0) or sigD<=0: return None
    d=abs(math.log(B/S))
    if d<=0: return 0.0
    return round(min((d/(sigD*_Q75))**2, cap),1)

def _dvol(c):
    r=[math.log(c[i]/c[i-1]) for i in range(1,len(c)) if c[i-1]>0 and c[i]>0]
    if len(r)<3: return None
    m=sum(r)/len(r); return (sum((x-m)**2 for x in r)/(len(r)-1))**0.5

def regime_flip_prob(closes):
    """P(volatility regime shifting): logistic of |log(short-vol / long-vol)| (10d vs 42d)."""
    if len(closes)<42: return None
    sv=_dvol(closes[-10:]); lv=_dvol(closes[-42:])
    if not sv or not lv or lv<=0: return None
    x=abs(math.log(sv/lv))
    return round(1.0/(1.0+math.exp(-(x-0.40)/0.25)),2)

def calibrate_touch(samples, T=21, lookback=150, win=63):
    """Reliability backtest of the up-touch model: at each past day t, predict P(touch the
    trailing-63d high within T days), then check whether it actually touched in (t,t+T].
    Returns reliability bins (predicted vs realized) + Brier score. Samples = list of close series."""
    bins=[[0.0,0,0] for _ in range(5)]; bn=bd=0.0; bcount=0
    for cl in samples:
        nN=len(cl)
        if nN<win+T+30: continue
        for t in range(nN-T-1, max(win, nN-T-1-lookback), -1):
            hist=cl[:t+1]; sp=hist[-1]; Bhi=max(hist[-win:]); sd=_dvol(hist[-win:])
            if not sd or sd<=0: continue
            p=prob_touch(sp,Bhi,sd,T); hit=1 if max(cl[t+1:t+1+T])>=Bhi else 0
            b=min(4,int(p*5)); bins[b][0]+=p; bins[b][1]+=1; bins[b][2]+=hit
            bn+=(p-hit)**2; bcount+=1
    out=[{"pmid":round((i+0.5)/5,2),"pred":round(sp_/nn,3),"real":round(hh/nn,3),"n":nn}
         for i,(sp_,nn,hh) in enumerate(bins) if nn>0]
    return {"bins":out,"brier":round(bn/bcount,4) if bcount else None,"n":bcount}

# ---------- synthetic seed (recognisable names, illustrative numbers) -------------------------
SEED=[("AAPL","Apple","Technology","ND S"),("MSFT","Microsoft","Technology","ND S"),("NVDA","NVIDIA","Technology","ND S"),
("AVGO","Broadcom","Technology","ND S"),("ORCL","Oracle","Technology","S"),("CRM","Salesforce","Technology","D S"),
("ADBE","Adobe","Technology","ND S"),("AMD","AMD","Technology","ND S"),("CSCO","Cisco","Technology","ND S"),
("INTC","Intel","Technology","ND S"),("IBM","IBM","Technology","D S"),("QCOM","Qualcomm","Technology","ND S"),
("TXN","Texas Instr.","Technology","ND S"),("NOW","ServiceNow","Technology","S"),("JPM","JPMorgan","Financials","D S"),
("BAC","Bank of America","Financials","S"),("WFC","Wells Fargo","Financials","S"),("GS","Goldman Sachs","Financials","D S"),
("MS","Morgan Stanley","Financials","S"),("V","Visa","Financials","D S"),("MA","Mastercard","Financials","S"),
("AXP","Amex","Financials","D S"),("BLK","BlackRock","Financials","S"),("C","Citigroup","Financials","S"),
("UNH","UnitedHealth","Health Care","D S"),("JNJ","Johnson & Johnson","Health Care","D S"),("LLY","Eli Lilly","Health Care","S"),
("PFE","Pfizer","Health Care","S"),("MRK","Merck","Health Care","D S"),("ABBV","AbbVie","Health Care","S"),
("TMO","Thermo Fisher","Health Care","S"),("AMGN","Amgen","Health Care","ND S"),("GILD","Gilead","Health Care","ND S"),
("ISRG","Intuitive","Health Care","ND S"),("AMZN","Amazon","Consumer Disc.","ND S"),("TSLA","Tesla","Consumer Disc.","ND S"),
("HD","Home Depot","Consumer Disc.","D S"),("MCD","McDonald's","Consumer Disc.","D S"),("NKE","Nike","Consumer Disc.","D S"),
("LOW","Lowe's","Consumer Disc.","S"),("SBUX","Starbucks","Consumer Disc.","ND S"),("BKNG","Booking","Consumer Disc.","ND S"),
("GOOGL","Alphabet","Communication","ND S"),("META","Meta","Communication","ND S"),("NFLX","Netflix","Communication","ND S"),
("DIS","Disney","Communication","D S"),("CMCSA","Comcast","Communication","ND S"),("T","AT&T","Communication","S"),
("VZ","Verizon","Communication","D S"),("TMUS","T-Mobile","Communication","ND S"),("CAT","Caterpillar","Industrials","D S"),
("BA","Boeing","Industrials","D S"),("HON","Honeywell","Industrials","ND S"),("GE","GE Aerospace","Industrials","S"),
("UNP","Union Pacific","Industrials","S"),("RTX","RTX","Industrials","S"),("DE","Deere","Industrials","S"),
("LMT","Lockheed","Industrials","S"),("UPS","UPS","Industrials","S"),("MMM","3M","Industrials","D S"),
("PG","Procter & Gamble","Consumer Staples","D S"),("KO","Coca-Cola","Consumer Staples","D S"),("PEP","PepsiCo","Consumer Staples","ND S"),
("WMT","Walmart","Consumer Staples","D S"),("COST","Costco","Consumer Staples","ND S"),("MDLZ","Mondelez","Consumer Staples","ND S"),
("CL","Colgate","Consumer Staples","S"),("PM","Philip Morris","Consumer Staples","S"),("XOM","Exxon Mobil","Energy","S"),
("CVX","Chevron","Energy","D S"),("COP","ConocoPhillips","Energy","S"),("SLB","Schlumberger","Energy","S"),
("EOG","EOG Resources","Energy","S"),("MPC","Marathon Pet.","Energy","S"),("NEE","NextEra","Utilities","S"),
("DUK","Duke Energy","Utilities","S"),("SO","Southern Co","Utilities","S"),("D","Dominion","Utilities","S"),
("AEP","American Elec.","Utilities","ND S"),("EXC","Exelon","Utilities","ND S"),("LIN","Linde","Materials","ND S"),
("SHW","Sherwin-Williams","Materials","D S"),("APD","Air Products","Materials","S"),("FCX","Freeport","Materials","S"),
("NEM","Newmont","Materials","S"),("DOW","Dow Inc","Materials","S"),("PLD","Prologis","Real Estate","S"),
("AMT","American Tower","Real Estate","S"),("EQIX","Equinix","Real Estate","ND S"),("SPG","Simon Property","Real Estate","S"),
("O","Realty Income","Real Estate","S"),("CCI","Crown Castle","Real Estate","S")]

# Representative Russell 2000 small/mid-cap cohort (illustrative for the sample; the nightly
# --real job replaces this with the actual iShares IWM holdings).
RUSSELL_SEED=[("RMBS","Rambus","Technology"),("FORM","FormFactor","Technology"),("POWI","Power Integrations","Technology"),
("SMTC","Semtech","Technology"),("CALX","Calix","Technology"),("EXTR","Extreme Networks","Technology"),
("PB","Prosperity Bancshares","Financials"),("GBCI","Glacier Bancorp","Financials"),("CADE","Cadence Bank","Financials"),
("UCBI","United Community Banks","Financials"),("ABCB","Ameris Bancorp","Financials"),("BANF","BancFirst","Financials"),
("HALO","Halozyme","Health Care"),("MMSI","Merit Medical","Health Care"),("CYTK","Cytokinetics","Health Care"),
("ARWR","Arrowhead Pharma","Health Care"),("KRYS","Krystal Biotech","Health Care"),("VCEL","Vericel","Health Care"),
("SHAK","Shake Shack","Consumer Disc."),("CROX","Crocs","Consumer Disc."),("BOOT","Boot Barn","Consumer Disc."),
("CAKE","Cheesecake Factory","Consumer Disc."),("TXRH","Texas Roadhouse","Consumer Disc."),("WING","Wingstop","Consumer Disc."),
("SAIA","Saia","Industrials"),("AAON","AAON","Industrials"),("MLI","Mueller Industries","Industrials"),
("AIT","Applied Industrial","Industrials"),("GVA","Granite Construction","Industrials"),("HRI","Herc Holdings","Industrials"),
("OLN","Olin","Materials"),("CMP","Compass Minerals","Materials"),("AVNT","Avient","Materials"),
("PR","Permian Resources","Energy"),("CIVI","Civitas Resources","Energy"),("MGY","Magnolia Oil & Gas","Energy"),
("CRK","Comstock Resources","Energy"),("NWE","NorthWestern Energy","Utilities"),("POR","Portland General","Utilities"),
("OGS","ONE Gas","Utilities"),("SR","Spire","Utilities"),("CARG","CarGurus","Communication"),
("CNK","Cinemark","Communication"),("TDS","Telephone & Data","Communication"),("IRT","Independence Realty","Real Estate"),
("STAG","Stag Industrial","Real Estate"),("CUZ","Cousins Properties","Real Estate"),("EPR","EPR Properties","Real Estate"),
("CENT","Central Garden","Consumer Staples"),("JJSF","J&J Snack Foods","Consumer Staples"),("FRPT","Freshpet","Consumer Staples")]

# ---- FACTOR PANEL: commodity / rate / sector / style / global proxies (ETF & index) for cross-asset
#      conditioning. Tagged idx=["FACTOR"] so the cross-section + cone can correlate every name against
#      the full macro complex (all commodities, the rate curve, every sector, styles) without polluting
#      the equity recommendation set. Robust yfinance symbols. ----
FACTOR_PANEL=[
  ("USO","WTI Crude","Commodity"),("BNO","Brent Crude","Commodity"),("UNG","Natural Gas","Commodity"),
  ("GLD","Gold","Commodity"),("SLV","Silver","Commodity"),("CPER","Copper","Commodity"),("PPLT","Platinum","Commodity"),
  ("PALL","Palladium","Commodity"),("DBB","Base Metals","Commodity"),("DBA","Agriculture","Commodity"),
  ("CORN","Corn","Commodity"),("WEAT","Wheat","Commodity"),("SOYB","Soybeans","Commodity"),("CANE","Sugar","Commodity"),
  ("JO","Coffee","Commodity"),("URA","Uranium","Commodity"),("LIT","Lithium","Commodity"),("REMX","Rare Earths","Commodity"),
  ("DBC","Broad Commodities","Commodity"),("GSG","Commodity Index","Commodity"),
  ("SHY","1-3y Treasury","Rate"),("IEF","7-10y Treasury","Rate"),("TLT","20y+ Treasury","Rate"),
  ("TIP","TIPS / breakevens","Rate"),("HYG","High Yield","Rate"),("LQD","Inv-Grade Credit","Rate"),("EMB","EM Bonds","Rate"),
  ("UUP","US Dollar (broad)","FX"),("UDN","US Dollar (bear)","FX"),("FXE","Euro","FX"),("FXY","Yen","FX"),
  ("FXB","British Pound","FX"),("FXF","Swiss Franc","FX"),("FXC","Canadian Dollar","FX"),("FXA","Aussie Dollar","FX"),("CEW","EM Currencies","FX"),
  ("XLK","Technology","Sector"),("XLF","Financials","Sector"),("XLV","Health Care","Sector"),("XLY","Consumer Disc.","Sector"),
  ("XLP","Consumer Staples","Sector"),("XLE","Energy","Sector"),("XLI","Industrials","Sector"),("XLB","Materials","Sector"),
  ("XLU","Utilities","Sector"),("XLRE","Real Estate","Sector"),("XLC","Communications","Sector"),
  ("SPY","S&P 500","Broad"),("QQQ","Nasdaq 100","Broad"),("IWM","Russell 2000","Broad"),("DIA","Dow","Broad"),("RSP","Equal-Weight S&P","Broad"),
  ("MTUM","Momentum","Style"),("QUAL","Quality","Style"),("VLUE","Value","Style"),("SIZE","Size","Style"),("USMV","Low Vol","Style"),
  ("IWF","Growth","Style"),("IWD","Value (R1000)","Style"),
  ("EFA","Developed ex-US","Global"),("EEM","Emerging Mkts","Global"),("FXI","China","Global"),("EWJ","Japan","Global"),("EWZ","Brazil","Global"),
]

def membership(code):
    p=code.split(); idx=[]
    if "ND" in p: idx.append("NDX")
    if "D" in p: idx.append("DOW")
    if "S" in p: idx.append("SPX")
    if "R" in p: idx.append("RUT")
    return sorted(set(idx)) or ["SPX"]

SECMACRO={"Energy":{"OIL":1.10,"NATGAS":0.55,"DXY":-0.20,"HYG":0.30},
 "Financials":{"RATE":0.55,"SLOPE":0.45,"DXY":0.10,"HYG":0.40},
 "Materials":{"OIL":0.45,"GOLD":0.55,"COPPER":0.60,"DXY":-0.30},
 "Utilities":{"RATE":-0.55,"NATGAS":0.25},"Real Estate":{"RATE":-0.60,"HYG":0.30},
 "Technology":{"RATE":-0.30,"VIX":-0.25,"COPPER":0.20},"Consumer Disc.":{"RATE":-0.20,"VIX":-0.25,"OIL":-0.20},
 "Communication":{"VIX":-0.20},"Industrials":{"OIL":0.25,"COPPER":0.45,"SLOPE":0.25},
 "Consumer Staples":{"VIX":0.10,"GOLD":0.10},"Health Care":{}}

SECVAL={"Technology":(34,0.18,19),"Communication":(22,0.12,11),"Consumer Disc.":(26,0.14,14),
        "Health Care":(24,0.10,15),"Industrials":(21,0.09,13),"Financials":(13,0.08,9),
        "Consumer Staples":(22,0.06,15),"Energy":(11,0.05,6),"Utilities":(18,0.04,11),
        "Materials":(15,0.07,8),"Real Estate":(30,0.05,18)}   # (base trailing P/E, earnings growth, base EV/EBITDA)

def _median(xs):
    xs=sorted(x for x in xs if x is not None and x==x)
    if not xs: return None
    m=len(xs)//2
    return xs[m] if len(xs)%2 else (xs[m-1]+xs[m])/2.0

def valuation_verdict(v, peSec, evSec):
    """Aggregate P/E + PEG + EV/adjusted-EBITDA + forward-vs-trailing multiple into SUPPORTED/REJECTED
    verdicts with full reasoning text. Pure deterministic; every clause is auditable."""
    if not v: return None
    pe=v.get("pe"); fpe=v.get("fpe"); peg=v.get("peg"); evb=v.get("evb"); epsg=v.get("epsg"); revg=v.get("revg")
    if peg is None and pe and epsg and epsg>0.003: peg=round(pe/(epsg*100.0),2)   # derive PEG if absent
    parts=[]; pegV=None; peV=None
    # --- PEG ---
    if peg is not None:
        if peg<=1.0: pegV="supported"; parts.append("PEG "+str(peg)+" ≤ 1.0 — earnings growth more than covers the multiple (cheap for growth)")
        elif peg<=2.0: pegV="supported"; parts.append("PEG "+str(peg)+" between 1.0 and 2.0 — multiple roughly fair for the growth rate")
        else: pegV="rejected"; parts.append("PEG "+str(peg)+" > 2.0 — price NOT justified by earnings growth (stretched)")
    elif pe is None:
        parts.append("No positive trailing earnings — P/E and PEG not meaningful; judge on EV/EBITDA and cash flow")
    else:
        parts.append("Earnings growth not positive — PEG undefined; P/E must stand on sector-relative value, not growth")
    # --- P/E vs sector + growth ---
    if pe is not None and peSec:
        rel=pe/peSec; relpct=int(round((rel-1)*100))
        loc=str(abs(relpct))+"% "+("premium to" if relpct>=0 else "discount to")+" sector "+str(round(peSec,1))
        if epsg is not None and epsg>0 and peg is not None and peg<=1.5:
            peV="supported"; parts.append("P/E "+str(pe)+" ("+loc+") is SUPPORTED by "+str(int(round(epsg*100)))+"% earnings growth")
        elif relpct>30 and (peg is None or peg>2.0):
            peV="rejected"; parts.append("P/E "+str(pe)+" sits "+str(relpct)+"% above sector "+str(round(peSec,1))+" without commensurate growth — REJECTED as rich")
        elif relpct< -10:
            peV="supported"; parts.append("P/E "+str(pe)+" is a "+loc+" — relatively cheap, supported")
        else:
            peV="supported"; parts.append("P/E "+str(pe)+" broadly in line with sector "+str(round(peSec,1))+" — supported")
    # --- projected (forward vs trailing) multiple ---
    if pe and fpe and pe>0:
        comp=int(round((fpe/pe-1)*100))
        parts.append("Projected multiple: forward P/E "+str(fpe)+" vs trailing "+str(pe)+" ("+("" if comp<0 else "+")+str(comp)+"%) — market prices "+("multiple COMPRESSION, i.e. earnings expected to grow into the price" if comp<0 else "multiple EXPANSION, i.e. earnings expected to fall or a re-rate higher"))
    # --- EV / adjusted EBITDA ---
    if evb and evSec:
        evrel=int(round((evb/evSec-1)*100))
        parts.append("Price-to-(adjusted) EBITDA: EV/EBITDA "+str(evb)+" vs sector "+str(round(evSec,1))+" ("+("" if evrel<0 else "+")+str(evrel)+"%)")
    if revg is not None and epsg is not None:
        corr="corroborated by" if (revg>0 and epsg>0) else "NOT corroborated by"
        parts.append("Earnings growth "+str(int(round(epsg*100)))+"% "+corr+" revenue growth "+str(int(round(revg*100)))+"%")
    _vd=[x for x in (peV,pegV) if x]
    overall=("n/a" if not _vd else "mixed" if ("rejected" in _vd and "supported" in _vd)
             else "rejected" if "rejected" in _vd else "supported")
    return {"pe":pe,"fpe":fpe,"peg":peg,"evb":evb,"epsg":epsg,"revg":revg,
            "peSec":round(peSec,1) if peSec else None,"evSec":round(evSec,1) if evSec else None,
            "peV":peV,"pegV":pegV,"overall":overall,"reason":". ".join(parts)+"."}

def synth(seed=7):
    rng=random.Random(seed); W=53
    mkt=[rng.gauss(0.002,0.022) for _ in range(W)]
    secf={s:[rng.gauss(0,0.012) for _ in range(W)] for s in SECTORS}
    ff={"SMB":[rng.gauss(0,0.01) for _ in range(W)],"HML":[rng.gauss(0,0.01) for _ in range(W)],"MOM":[rng.gauss(0,0.01) for _ in range(W)]}
    macro={"DXY":[rng.gauss(0,0.008) for _ in range(W)],"RATE":[rng.gauss(0,0.012) for _ in range(W)],
           "VIX":[rng.gauss(0,0.05) for _ in range(W)],"OIL":[rng.gauss(0,0.03) for _ in range(W)],
           "HYG":[rng.gauss(0,0.006) for _ in range(W)],"GOLD":[rng.gauss(0,0.02) for _ in range(W)],
           "COPPER":[rng.gauss(0,0.025) for _ in range(W)],"NATGAS":[rng.gauss(0,0.05) for _ in range(W)],
           "SLOPE":[rng.gauss(0,0.012) for _ in range(W)]}
    names=[]
    def mk(sym,nm,sec,idx,mcaprange,idiorange,liquid):
        b=rng.uniform(*[0.6,1.6] if liquid else [0.7,1.9]); sl=rng.uniform(0.5,1.2)
        cs,ch,cm=rng.uniform(-0.8,0.8),rng.uniform(-0.8,0.8),rng.uniform(-0.6,0.6); idio=rng.uniform(*idiorange)
        mb={f:SECMACRO.get(sec,{}).get(f,0.0)+rng.gauss(0,0.10) for f in ("DXY","RATE","VIX","OIL","HYG","GOLD","COPPER","NATGAS","SLOPE")}
        wr=[b*mkt[w]+sl*secf[sec][w]+cs*ff["SMB"][w]+ch*ff["HML"][w]+cm*ff["MOM"][w]
            +sum(mb[f]*macro[f][w] for f in mb)+rng.gauss(0,idio) for w in range(W)]
        mcap=math.exp(rng.uniform(*mcaprange))
        px=100.0; closes=[]; highs=[]; lows=[]; vols=[]
        for w in range(W):
            for _ in range(5):
                dr=wr[w]/5+rng.gauss(0,idio/2); px*=(1+dr); u=rng.uniform(0.003,0.02)
                closes.append(px); highs.append(px*(1+u)); lows.append(px*(1-u))
                vols.append(rng.uniform(0.6,1.8)*mcap*(0.0008 if liquid else 0.0012)*(1+abs(dr)*8))
        fcf=mcap*rng.uniform(-0.02,0.08) if liquid else mcap*rng.uniform(-0.05,0.07)
        _bpe,_bg,_bev=SECVAL.get(sec,(20,0.08,12))
        _pe=max(5.0,_bpe*rng.uniform(0.6,1.6)); _eg=max(-0.06,_bg+rng.gauss(0,0.05))
        if rng.random()<0.10: _pe=None                      # ~10% unprofitable (no positive earnings)
        _fpe=(round(_pe/(1+max(_eg,0.0)),1) if (_pe and _eg>0) else (round(_pe*rng.uniform(0.95,1.1),1) if _pe else None))
        _peg=(round(_pe/(_eg*100.0),2) if (_pe and _eg>0.003) else None)
        valr={"pe":round(_pe,1) if _pe else None,"fpe":_fpe,"peg":_peg,
              "evb":round(max(3.0,_bev*rng.uniform(0.6,1.7)),1),"epsg":round(_eg,3),"revg":round(max(-0.06,_eg*rng.uniform(0.4,1.1)),3)}
        rec={"t":sym,"n":nm,"sec":sec,"idx":idx,"mcap":round(mcap),
             "wr":[round(x,5) for x in wr],"_cl":closes,"_hi":highs,"_lo":lows,"_vol":vols,"_fcf":fcf,"_val":valr}
        _iv=rng.random()
        if _iv<0.22: rec["insider"]={"verdict":"insider buying (signal)","score":round(rng.uniform(0.3,1.0),2),"buy":int(rng.uniform(1,8)*1e6),"discSell":0,"planSell":int(rng.uniform(0,3)*1e6),"buyers":rng.randint(1,3),"sellers":0,"days":120}
        elif _iv<0.5: rec["insider"]={"verdict":"routine 10b5-1 selling (noise)","score":0.0,"buy":0,"discSell":0,"planSell":int(rng.uniform(1,12)*1e6),"buyers":0,"sellers":0,"days":120}
        elif _iv<0.64: rec["insider"]={"verdict":"discretionary selling (caution)","score":round(rng.uniform(-1.0,-0.2),2),"buy":0,"discSell":int(rng.uniform(1,9)*1e6),"planSell":int(rng.uniform(0,4)*1e6),"buyers":0,"sellers":rng.randint(1,3),"days":120}
        else: rec["insider"]={"verdict":"quiet","score":0.0,"buy":0,"discSell":0,"planSell":0,"buyers":0,"sellers":0,"days":120}
        _qv=rng.random(); _h=rng.randint(40,2200); _sh=int(rng.uniform(5,900)*1e6); _vv=int(rng.uniform(0.5,80)*1e9)
        if _qv<0.33: rec["inst"]={"verdict":"accumulation","dShares":round(rng.uniform(2,18),1),"dHolders":rng.randint(1,40),"holders":_h,"shares":_sh,"value":_vv}
        elif _qv<0.6: rec["inst"]={"verdict":"distribution","dShares":round(rng.uniform(-18,-2),1),"dHolders":-rng.randint(1,35),"holders":_h,"shares":_sh,"value":_vv}
        else: rec["inst"]={"verdict":"stable","dShares":round(rng.uniform(-1.8,1.8),1),"dHolders":rng.randint(-5,5),"holders":_h,"shares":_sh,"value":_vv}
        _sp=rec["_cl"][-1] if rec.get("_cl") else 100.0; _reg=rng.random()
        rec["gex"]={"gexTotal":int(rng.uniform(-9,9)*1e6),"regime":("positive (pinning/mean-revert)" if _reg<0.55 else "negative (amplifying/trend)"),
                    "wallUp":round(_sp*rng.uniform(1.02,1.12),2),"wallDn":round(_sp*rng.uniform(0.88,0.98),2),
                    "flip":round(_sp*rng.uniform(0.96,1.04),2),"atmIV":round(rng.uniform(15,70),1),
                    "expMovePct":round(rng.uniform(3,14),2),"pcr":round(rng.uniform(0.5,1.8),2),"skew":round(rng.uniform(-0.02,0.08),3),"days":30}
        _sq=rng.random()
        rec["short"]=({"fails":int(rng.uniform(1,12)*1e5),"prevFails":int(rng.uniform(1,12)*1e5),"trend":("rising" if _sq<0.3 else "falling" if _sq<0.55 else "flat"),"level":("elevated" if _sq<0.2 else "moderate" if _sq<0.6 else "low")} if _sq<0.8 else None)
        if liquid and rng.random()<0.85:                 # liquid names carry an options chain
            sp=closes[-1]; rec["_opt"]={"pw":round(sp*rng.uniform(0.88,0.97),2),"cw":round(sp*rng.uniform(1.03,1.12),2),
                                        "pcr":round(rng.uniform(0.6,1.7),2),"gex":round(sp*rng.uniform(0.97,1.03),2)}
        return rec
    for sym,nm,sec,code in SEED:
        names.append(mk(sym,nm,sec,membership(code),[23.5,28.8],[0.01,0.03],True))
    for sym,nm,sec in RUSSELL_SEED:
        names.append(mk(sym,nm,sec,["RUT"],[20.4,24.2],[0.025,0.055],False))
    return names,mkt,ff,macro

def aggregate(wr):
    def cum(k):
        s=wr[-k:] if k<=len(wr) else wr; p=1.0
        for x in s: p*=(1+x)
        return (p-1)*100
    return {"1w":round(wr[-1]*100,2) if wr else 0,"1m":round(cum(4),2),"3m":round(cum(13),2),"6m":round(cum(26),2),"12m":round(cum(52),2)}

def build(names,mkt,ff,macro=None):
    macro=macro or {}
    # Normalize every series to a common trailing length so real-data tickers with
    # different listing histories align (synthetic data is already uniform). Guards the
    # OLS factor regression (mkt[w]) and the sector-mean loop against ragged arrays.
    L=min([len(mkt)]+[len(n["wr"]) for n in names if n.get("wr")] or [0])
    if L>2:
        mkt=mkt[-L:]; ff={k:(v[-L:] if len(v)>=L else v+[0.0]*(L-len(v))) for k,v in ff.items()}
        macro={k:(v[-L:] if len(v)>=L else v+[0.0]*(L-len(v))) for k,v in macro.items()}
        for n in names: n["wr"]=n["wr"][-L:]
    # Commodity attribution set: ALL commodity driver series present in macro (FMP Ultimate
    # surfaces ~30 via commodityKeys; the legacy proxy path supplies the named handful).
    # Data-driven so every commodity flows into the Lasso candidates, the dependency factors,
    # the macro3 top-3 pool, and the factor covariance — not a hardcoded subset.
    _COMLAB=globals().get("_COMMODITY_LABELS") or {}
    _LEGACY_COM=("OIL","BRENT","NATGAS","GOLD","SILVER","COPPER","PLATINUM","PALLADIUM","ALUMINUM","CORN","WHEAT","SOYBEAN","COFFEE","SUGAR")
    _COMKEYS=[k for k in (list(_COMLAB.keys()) or list(_LEGACY_COM)) if k in macro and len(macro[k])==len(mkt)]
    MFAC=[f for f in ("DXY","RATE","VIX") if f in macro and len(macro[f])==len(mkt)]+_COMKEYS
    _calib=[]
    for n in names:
        wr=[x if (x is not None and x==x) else 0.0 for x in n["wr"]]; n["wr"]=wr; n["ret"]=aggregate(wr)
        _v=ann_vol(wr); _b=beta(wr,mkt)
        n["vol"]=round(_v*100,1) if _v==_v else 0.0; n["beta"]=round(_b,2) if _b==_b else 1.0
        X=[[mkt[w],ff["SMB"][w],ff["HML"][w],ff["MOM"][w]] for w in range(len(wr))]
        bc=ols_betas(wr,X); n["ff"]={f:(round(bc[i],2) if bc[i]==bc[i] else 0.0) for i,f in enumerate(FACTORS)}
        cl=n.pop("_cl",None); vo=n.pop("_vol",None)
        def _ri(x):                                          # NaN-safe int round
            return round(x) if (x is not None and x==x) else 0
        def _rf(x,nd):                                       # NaN-safe float round
            return round(x,nd) if (x is not None and x==x) else 0.0
        if cl and vo:
            net1,i1,o1,li,lo=money_flow(cl[-21:],vo[-21:]); net3,_,_,_,_=money_flow(cl[-63:],vo[-63:])
            n["flow"]={"net1m":_rf(net1,3),"net3m":_rf(net3,3),"in":_ri(i1),"out":_ri(o1),"din":_ri(li),"dout":_ri(lo)}
        else:
            n["flow"]={"net1m":0.0,"net3m":0.0,"in":0,"out":0,"din":0,"dout":0}
        fcf=n.pop("_fcf",None); n["fcf"]=round(fcf) if fcf is not None else None
        n["fcfY"]=round(fcf/n["mcap"]*100,2) if (fcf is not None and n["mcap"]) else None
        # MFI (0..100) + ATR% + breakout flag from daily High/Low/Close/Volume
        hi=n.pop("_hi",None); lo=n.pop("_lo",None); n["opt"]=n.pop("_opt",None); a=float("nan")
        if cl and lo and hi and vo and len(cl)>15:
            mv=mfi(hi,lo,cl,vo,14); a=atr(hi,lo,cl,14)
            n["mfi"]=round(mv,1) if mv==mv else 50.0
            n["atr"]=round(a/cl[-1]*100,2) if (a==a and cl[-1]) else 0.0
            n["brk"]=1 if (len(cl)>=2 and a==a and cl[-1]<cl[-2]-a) else 0
        else:
            n["mfi"]=50.0; n["atr"]=0.0; n["brk"]=0
        # Phase-3 registry adds: half-life (P3-33), variance ratio (P3-25), Parkinson range vol (P3-19), jump fraction (P3-20)
        n["hl"]=half_life(cl) if (cl and len(cl)>25) else None
        n["vr"]=variance_ratio(cl) if (cl and len(cl)>=20) else None
        n["jump"]=jump_ratio(cl) if (cl and len(cl)>=9) else None
        # Quarterly-timeline analyst metrics (verified quarterly_timeline.py): drawdown depth + recovery + downside vol
        try:
            import quarterly_timeline as _qt
            if cl and len(cl) > 30:
                _ddq = _qt.drawdowns(cl); n["maxDD"] = round(_ddq["maxDD"] * 100, 1)
                _eps = _ddq.get("episodes") or []
                n["ddRec"] = (_eps[-1].get("recoveryDays") if (_eps and _eps[-1].get("recoveryDays") is not None) else None)
                _lr = _qt.log_returns(cl)
                if len(_lr) > 5:
                    n["dvol"] = round(_qt.downside_vol(_lr) * 100, 1)
        except Exception:
            pass
        # Intraday/relative volume pace: latest-bar volume vs trailing-20 median (>1 = running hot).
        # During the 3pm-ET intraday refresh the latest bar is today's partial, so this reads intraday pace.
        try:
            if vo and len(vo) > 21:
                _v20 = sorted(vo[-21:-1]); _med = _v20[len(_v20) // 2] if _v20 else 0
                n["rvol"] = round(vo[-1] / _med, 2) if _med else None
        except Exception:
            pass
        _pv=parkinson_vol(hi,lo) if (hi and lo) else None
        n["pvol"]=round(_pv*math.sqrt(252)*100,1) if _pv else None      # annualized Parkinson vol %
        vr=n["vr"]
        n["regime"]=("trending" if (vr is not None and vr>=1.15) else
                     "mean-revert" if (vr is not None and vr<=0.85) else
                     "random-walk" if vr is not None else None)
        # Sparse macro attribution (Lasso) + dislocation residual (decoupling from macro beta)
        if MFAC and len(wr)>=8:
            cols=[mkt]+[macro[f] for f in MFAC]; fac=["MKT"]+MFAC
            Xr=[[cols[c][w] for c in range(len(cols))] for w in range(len(wr))]
            bl=lasso_cd(wr,Xr,alpha=0.08)
            n["mb"]={fac[c]:round(bl[c],2) for c in range(len(fac)) if abs(bl[c])>=0.05}
            n["drv"]=max(n["mb"],key=lambda f:abs(n["mb"][f])) if n["mb"] else None
            _,res=macro_fit(wr,cols)
            rmean=sum(res)/len(res); rstd=(sum((x-rmean)**2 for x in res)/len(res))**0.5 or 1.0
            n["_disloc"]=(sum(res[-4:])/4.0)/rstd*2.0
        else:
            n["mb"]={}; n["drv"]=None; n["_disloc"]=0.0
        # EMA21-first decision metrics: distance %, distance in sigma, 5-day slope, threshold ladder + prob-of-touch
        if cl and len(cl)>=22:
            es=ema_series(cl,21); e21=es[-1]; sp=cl[-1]; sdl=daily_logvol(cl)
            if n.get("gex") and n["gex"].get("atmIV") and sdl==sdl and sdl>0:
                _ivd=n["gex"]["atmIV"]/100.0/math.sqrt(252)        # implied daily sigma -> blend 50/50 into forward odds
                if _ivd>0: sdl=0.5*sdl+0.5*_ivd
            n["ema21d"]=round((sp-e21)/e21*100,2) if e21 else 0.0
            n["ema21sig"]=round(((sp-e21)/e21)/(sdl*math.sqrt(21)),2) if (e21 and sdl==sdl and sdl>0) else 0.0
            e5=es[-6] if (len(es)>=6 and es[-6]) else None
            n["ema21sl"]=round((e21-e5)/e5*100,2) if e5 else 0.0
            win=cl[-63:] if len(cl)>=63 else cl; Bhi=max(win); Blo=min(win); mean63=sum(win)/len(win)
            au=(Bhi-sp)/a if (a==a and a>0) else None; ad=(sp-Blo)/a if (a==a and a>0) else None
            n["touch"]={"up":{"d":round(au,2) if au is not None else None,"p":round(prob_touch(sp,Bhi,sdl,21),2) if sdl==sdl else None},
                        "dn":{"d":round(ad,2) if ad is not None else None,"p":round(prob_touch(sp,Blo,sdl,21),2) if sdl==sdl else None}}
            # ODDS LADDER: forward first-passage probabilities over a 21-day horizon (model-implied, driftless)
            def _pt(B): return round(prob_touch(sp,B,sdl,21),2) if (sdl==sdl and sdl>0) else None
            pHi=_pt(Bhi); pLo=_pt(Blo)
            dHi=dLo=None                                  # idea 2: odds drift vs yesterday
            if len(cl)>=64 and sdl==sdl:
                cy=cl[:-1]; spy=cy[-1]; wy=cy[-63:]; sdy=daily_logvol(cy)
                if sdy==sdy and sdy>0:
                    if pHi is not None: dHi=round(pHi-prob_touch(spy,max(wy),sdy,21),2)
                    if pLo is not None: dLo=round(pLo-prob_touch(spy,min(wy),sdy,21),2)
            up=(Bhi/sp-1)*100; dn=(1-Blo/sp)*100          # idea 3: expected-value edge %
            ev=round((pHi or 0)*up-(pLo or 0)*dn,2)
            condHi=pHi                                    # idea 4: P(new high | +1sigma favorable macro driver)
            if n.get("drv") and n.get("mb") and sdl==sdl:
                shift=abs(n["mb"].get(n["drv"],0.0))*sdl*math.sqrt(5)
                if shift>0: condHi=round(prob_touch(sp*(1+shift),Bhi,sdl,21),2)
            n["odds"]={"ema":_pt(e21),"emaDir":("reclaim" if sp<e21 else "lose-support"),
                       "hi":pHi,"lo":pLo,"mean":_pt(mean63),"meanDir":("up" if sp<mean63 else "down"),
                       "beat":n.pop("_beat",None),
                       "drift":{"hi":dHi,"lo":dLo},
                       "tmed":{"hi":median_touch_days(sp,Bhi,sdl),"lo":median_touch_days(sp,Blo,sdl)},
                       "condHi":condHi,"flip":regime_flip_prob(cl)}     # idea 6: regime-flip odds
            n["ev"]=ev
            if len(_calib)<60 and "RUT" not in n.get("idx",[]) and len(cl)>140: _calib.append(cl)
        else:
            n["ema21d"]=0.0; n["ema21sig"]=0.0; n["ema21sl"]=0.0; n["touch"]=None; n["odds"]=None; n["ev"]=0.0
    val=[ -n["ret"]["12m"]/(n["vol"] or 1) for n in names]; mom=[n["ret"]["6m"] for n in names]
    risk=[n["beta"] for n in names]; size=[math.log(n["mcap"] or 1) for n in names]   # factor ETFs carry mcap=0 -> log(1)=0 (smallest bubble), avoids math domain error
    fcy=[n["fcfY"] for n in names]; flw=[n["flow"]["net1m"] for n in names]
    dis=[n.get("_disloc",0.0) for n in names]; mfv=[n.get("mfi",50.0) for n in names]; emv=[n.get("ema21sig",0.0) for n in names]
    Z=lambda a:zscores(winsorize(a))
    zV,zM,zR,zS,zF,zL=Z(val),Z(mom),Z(risk),Z(size),Z(fcy),Z(flw)
    zD,zMF,zE=Z(dis),Z(mfv),Z(emv)
    for i,n in enumerate(names):
        n["z"]={"val":round(zV[i],2),"mom":round(zM[i],2),"risk":round(zR[i],2),"size":round(zS[i],2),
                "fcf":round(zF[i],2),"flow":round(zL[i],2),"disloc":round(zD[i],2),"mfi":round(zMF[i],2),"ema":round(zE[i],2)}
        n["disloc"]=round(zD[i],2); n.pop("_disloc",None)
    cvals=[]
    for n in names:    # P3-42 contradiction: weighted agreement across the decision signals
        sigs=[("momentum",n["z"].get("mom",0),1.0),("flow",n["flow"].get("net1m",0),1.0),
              ("value",n["z"].get("val",0),0.8),("MFI",(n.get("mfi",50)-50),0.6),
              ("trend",n.get("ema21d",0),1.0)]
        cs,cdir,conf=contradiction(sigs); n["contra"]={"s":cs,"dir":cdir,"conf":conf[:3]}; cvals.append(cs)
    zC=Z(cvals)
    for i,n in enumerate(names): n["z"]["contra"]=round(zC[i],2)
    import bisect                                   # idea 7: cross-sectional percentile of the EV edge
    evs=sorted(n.get("ev",0.0) for n in names)
    for n in names:
        n["evPct"]=int(round(100.0*bisect.bisect_right(evs,n.get("ev",0.0))/len(evs))) if evs else 50
        o=n.get("odds") or {}; al=[]               # idea 8: odds-triggered alerts
        if o.get("hi") is not None and o["hi"]>=0.6: al.append("breakout odds "+str(round(o["hi"]*100))+"%")
        if o.get("lo") is not None and o["lo"]>=0.6: al.append("breakdown odds "+str(round(o["lo"]*100))+"%")
        if n.get("ev",0)>=3: al.append("positive edge +"+str(n["ev"])+"%")
        if o.get("beat") is not None and o["beat"]>=0.7: al.append("likely beat "+str(round(o["beat"]*100))+"%")
        if o.get("flip") is not None and o["flip"]>=0.7: al.append("vol regime shifting")
        if n.get("brk"): al.append("ATR breakout")
        if n.get("jump") is not None and n["jump"]>=0.5: al.append("recent jump (event-driven)")
        if n.get("regime")=="mean-revert" and abs(n.get("ema21d",0))>=4: al.append("mean-revert setup ("+("rich" if n.get("ema21d",0)>0 else "cheap")+" vs EMA21)")
        if n.get("insider") and n["insider"].get("verdict","").startswith("insider buying") and n["insider"].get("score",0)>=0.4: al.append("insider buying")
        if n.get("insider") and "caution" in n["insider"].get("verdict",""): al.append("insider selling")
        if n.get("inst") and n["inst"].get("verdict")=="accumulation" and (n["inst"].get("dShares") or 0)>=5: al.append("institutional accumulation")
        if n.get("inst") and n["inst"].get("verdict")=="distribution" and (n["inst"].get("dShares") or 0)<=-5: al.append("institutional distribution")
        if n.get("gex") and "negative" in (n["gex"].get("regime") or ""): al.append("negative gamma (trend-amplifying)")
        if n.get("short") and n["short"].get("trend")=="rising" and n["short"].get("level")=="elevated": al.append("rising fails (squeeze watch)")
        if n.get("contra") and n["contra"]["s"]<=0.2 and n.get("ema21d",0)>0: al.append("aligned uptrend")
        n["alerts"]=al[:5]
    peBySec={}; evBySec={}
    for n in names:
        v=n.get("_val") or {}
        if v.get("pe") is not None: peBySec.setdefault(n["sec"],[]).append(v["pe"])
        if v.get("evb") is not None: evBySec.setdefault(n["sec"],[]).append(v["evb"])
    peMed={s:_median(xs) for s,xs in peBySec.items()}; evMed={s:_median(xs) for s,xs in evBySec.items()}
    for n in names:
        n["val"]=valuation_verdict(n.pop("_val",None), peMed.get(n["sec"]), evMed.get(n["sec"]))
    secmean={}
    for s in SECTORS:
        mem=[n["wr"] for n in names if n["sec"]==s]
        if mem: secmean[s]=[sum(m[w] for m in mem)/len(mem) for w in range(len(mem[0]))]
    osec=[s for s in SECTORS if s in secmean]
    M=[[round(pearson(secmean[a],secmean[b]),3) for b in osec] for a in osec]
    oi=cluster_order(M); osec=[osec[i] for i in oi]; M=[[M[i][j] for j in oi] for i in oi]
    # ---- directional dependency list: which macro deltas / sector the name moves WITH or AGAINST ----
    FACS=[("MKT",mkt,"S&P 500"),("RATE",macro.get("RATE"),"10Y yield"),("DXY",macro.get("DXY"),"US dollar"),
          ("VIX",macro.get("VIX"),"VIX"),("HYG",macro.get("HYG"),"credit (HYG)"),("SLOPE",macro.get("SLOPE"),"2s10s slope")]
    _COMDISP={"OIL":"WTI oil","GOLD":"gold","COPPER":"copper","NATGAS":"nat gas","SILVER":"silver","BRENT":"Brent oil",
              "PLATINUM":"platinum","PALLADIUM":"palladium","ALUMINUM":"aluminum","CORN":"corn","WHEAT":"wheat",
              "SOYBEAN":"soybeans","COFFEE":"coffee","SUGAR":"sugar"}
    def _comdisp(ck): return _COMLAB.get(ck) or _COMDISP.get(ck) or ck.replace("_"," ").title()
    for _ck in _COMKEYS:                                 # EVERY commodity -> a dependency factor
        if macro.get(_ck): FACS.append((_ck, macro.get(_ck), _comdisp(_ck)))
    _fcov=None
    try:
        if _lineage is not None:
            _fcov=_lineage.factor_covariance({lab:ser for fk,ser,lab in FACS if ser})
    except Exception:
        _fcov=None
    EXPSIGN={"_base":{"MKT":1,"VIX":-1,"HYG":1},
      "Energy":{"OIL":1,"NATGAS":1,"DXY":-1},"Financials":{"RATE":1,"SLOPE":1,"DXY":1},
      "Materials":{"OIL":1,"GOLD":1,"COPPER":1,"DXY":-1},"Utilities":{"RATE":-1},"Real Estate":{"RATE":-1},
      "Technology":{"RATE":-1,"VIX":-1},"Consumer Disc.":{"RATE":-1,"VIX":-1},"Communication":{"VIX":-1},
      "Industrials":{"OIL":1,"COPPER":1,"SLOPE":1},"Consumer Staples":{},"Health Care":{}}
    def exp_sign(sec,fk):
        if fk=="SECTOR": return 1
        o=EXPSIGN.get(sec,{}).get(fk)
        return o if o is not None else EXPSIGN["_base"].get(fk,0)
    def best_lag(y,x,maxlag=2):
        base=pearson(y,x); best=(0, base if base==base else 0.0)
        for k in range(1,maxlag+1):
            if len(y)>k+8:
                c=pearson(y[k:], x[:len(x)-k])
                if c==c and abs(c)>abs(best[1])+0.05: best=(k,c)   # require real improvement to claim a lead
        return best
    def _dep(wr,ser,lab,sec,fk,is_mkt=False):
        c=pearson(wr,ser); n_obs=len([1 for a,b in zip(wr,ser) if a==a and b==b])
        if c!=c or n_obs<8: return None
        t=c*math.sqrt(max(n_obs-2,1)/max(1-c*c,1e-9)) if abs(c)<0.999 else 9.9
        sig=abs(t)>=1.96
        pc=c if is_mkt else partial_corr(wr,ser,mkt)
        sens=beta(wr,ser)*math.sqrt(_var(ser))
        h=len(wr)//2; rc=pearson(wr[-h:],ser[-h:])
        if rc==rc and c!=0 and rc*c<0 and abs(rc)>0.1: stab="flipped"
        elif rc==rc and abs(rc)<0.5*abs(c): stab="fading"
        else: stab="stable"
        lg,lc=best_lag(wr,ser)                              # lead/lag: factor leads stock by lg weeks
        es=exp_sign(sec,fk); unexp=bool(es!=0 and ((1 if c>0 else -1)!=es))   # sign vs economic prior
        pval=_t_two_sided_p(t, max(n_obs-2,1))                                # exact two-sided Student-t p (ν=n-2)
        return {"f":lab,"corr":round(c,2),"pcorr":round(pc,2) if pc==pc else None,
                "sens":round(sens*100,2),"sig":bool(sig),"p":round(pval,4),"stab":stab,"dir":("with" if c>0 else "against"),
                "lag":lg,"unexp":unexp}
    for n in names:
        wr=n["wr"]; deps=[]
        for fk,ser,lab in FACS:
            if not ser: continue
            d=_dep(wr,ser,lab,n["sec"],fk,fk=="MKT")
            if d: deps.append(d)
        sc=secmean.get(n["sec"])
        if sc:
            d=_dep(wr,sc,n["sec"]+" sector",n["sec"],"SECTOR")
            if d: deps.append(d)
        # Benjamini-Yekutieli FDR (q=0.10) across the ~36 per-name factor tests. BY (not BH) because the
        # candidate factors are arbitrarily DEPENDENT — the 30 commodities are heavily collinear — so the
        # harmonic-number penalty c(m)=Σ(1/i) is required to actually control the false-discovery rate.
        if deps:
            _order=sorted(range(len(deps)), key=lambda i: deps[i].get("p",1.0))
            _m=len(_order); _Hm=sum(1.0/_i for _i in range(1,_m+1)); _thr=0
            for _rank,_i in enumerate(_order,1):
                if deps[_i].get("p",1.0) <= 0.10*_rank/(_m*_Hm): _thr=_rank
            _crit=deps[_order[_thr-1]].get("p",1.0) if _thr>0 else -1.0
            for d in deps: d["sig"]=bool(d.get("p",1.0)<=_crit)
        keep=[d for d in deps if d["sig"]] or sorted(deps,key=lambda d:-abs(d["corr"]))[:1]
        keep.sort(key=lambda d:-(abs(d["pcorr"]) if d.get("pcorr") is not None else abs(d["corr"])))
        n["deps"]=keep[:7]
        # ---- macro3: ALWAYS-present rate-family driver + top-3 rate/commodity drivers ----
        # (decoupled from the significance-filtered deps so the terminal's interest-rate
        #  impact block can always rate the rate channel, even when it is weak.)
        def _slim(d):
            return {"f":d["f"],"sens":d["sens"],"corr":d["corr"],"pcorr":d.get("pcorr"),
                    "sig":bool(d.get("sig")),"stab":d.get("stab"),"dir":d.get("dir"),
                    "weak":(not bool(d.get("sig")))}
        _byf={d["f"]:d for d in deps}
        _rate=None
        for _w in ("10Y yield","2s10s slope"):          # 10Y -> 2s10s fallback chain
            if _w in _byf: _rate=_byf[_w]; break
        if _rate is None:                                 # last resort: the name's own sector driver
            for d in deps:
                if str(d.get("f","")).endswith(" sector"): _rate=d; break
        _RC={"10Y yield","2s10s slope"}|{_comdisp(_ck) for _ck in _COMKEYS}   # rate family + ALL commodities
        _pool=[d for d in deps if d["f"] in _RC]
        _pool.sort(key=lambda d:-(abs(d["pcorr"]) if d.get("pcorr") is not None else abs(d.get("corr") or 0)))
        n["macro3"]={"rate":(_slim(_rate) if _rate else None),
                     "top":[_slim(d) for d in _pool[:3]]}
        # ---- Phase 2: server-side regime-lineage object (HMM -> branches + LoTV split) ----
        if _lineage is not None and "FACTOR" not in (n.get("idx") or []):
            try:
                _lin=_lineage.lineage_object(wr)
                if _lin: n["lineage"]=_lin
            except Exception:
                pass
            # ---- Second/Third Build: causal (DML) + EVT/tail + factor decomp + Black-Litterman ----
            try:
                _facs={lab:ser for fk,ser,lab in FACS if ser and len(ser)==len(wr)}
                if len(_facs)>=2:
                    _cs=_lineage.causal_support(wr,_facs)
                    if _cs: n["causal"]=_cs
                _L=n.get("lineage")
                if isinstance(_L,dict):
                    _ev=_lineage.evt_gpd_tail(wr)
                    if _ev: _L["evt"]=_ev
                    if mkt and len(mkt)==len(wr):
                        _td=_lineage.tail_dependence(wr,mkt)
                        if _td: _L["tailDep"]=_td
                    if len(_facs)>=2:
                        _fd=_lineage.factor_decomp(wr,_facs,_fcov)
                        if _fd: _L["factor"]=_fd
                    _hm=sum(wr)/len(wr) if wr else 0.0
                    _hv=(sum((x-_hm)**2 for x in wr)/max(1,len(wr)-1)) if len(wr)>2 else 1e-4
                    _STP={"intraday":0.25,"1d":1,"5d":5,"10d":10,"20d":20,"63d":63}
                    _dsig=math.sqrt(_hv)/math.sqrt(5.0)
                    _L["impact"]={"impactBps":round(1e4*_lineage.sqrt_impact(_dsig,0.1),2),"participation":0.1,"law":"sqrt(Q/ADV)"}
                    _bl={"hist":{"mean":round(_hm,6),"var":round(_hv,8)},"horizons":{},
                         "viewIds":["regime-conditional"],"entropyApplied":False}
                    for _lab,_H in (_L.get("horizons") or {}).items():
                        _st=_STP.get(_lab,5)/5.0
                        _b=_lineage.black_litterman(_hm*_st, max(_hv*_st,1e-9),
                              [{"q":_H.get("mapDrift",0.0),"omega":max((_H.get("mapVol",0.0))**2,1e-9)}])
                        _bl["horizons"][_lab]=_b
                    _L["bl"]=_bl
            except Exception:
                pass
            # ---- Second/Third Build: causal macro-support (DML) + EVT/t-copula tail ----
            try:
                _facs={lab:ser for fk,ser,lab in FACS if ser and len(ser)==len(wr)}
                if len(_facs)>=2:
                    _cs=_lineage.causal_support(wr,_facs)
                    if _cs: n["causal"]=_cs
                if isinstance(n.get("lineage"),dict):
                    _ev=_lineage.evt_gpd_tail(wr)
                    if _ev: n["lineage"]["evt"]=_ev
                    if mkt and len(mkt)==len(wr):
                        _td=_lineage.tail_dependence(wr,mkt)
                        if _td: n["lineage"]["tailDep"]=_td
            except Exception:
                pass
        cols=[mkt]+[macro[f] for f in ("RATE","DXY","OIL","VIX") if macro.get(f)]
        _,res=macro_fit(wr,cols); vy=_var(wr)
        n["macroR2"]=int(round(max(0.0,1.0-_var(res)/vy)*100)) if vy>0 else 0
    # ---- opportunity rank: market position + momentum + sector-relative strength + EV edge ----
    secmom={}
    for sct in SECTORS:
        mem=[x["ret"]["3m"] for x in names if x["sec"]==sct]
        if mem: secmom[sct]=sum(mem)/len(mem)
    for n in names: n["secRel"]=round(n["ret"]["3m"]-secmom.get(n["sec"],0.0),2)
    zP=zscores(winsorize([n.get("ema21sig",0.0) for n in names]))
    zM2=[n["z"].get("mom",0.0) for n in names]
    zSR=zscores(winsorize([n["secRel"] for n in names]))
    zEV=zscores(winsorize([n.get("ev",0.0) for n in names]))
    oppv=[0.30*zP[i]+0.25*zM2[i]+0.25*zSR[i]+0.20*zEV[i] for i in range(len(names))]
    import bisect as _bis; oppr=sorted(oppv)
    for i,n in enumerate(names):
        n["opp"]=round(oppv[i],2)
        n["oppPct"]=int(round(100.0*_bis.bisect_right(oppr,oppv[i])/len(oppr))) if oppr else 50
    cal=calibrate_touch(_calib)                    # idea 1: reliability backtest of the touch model
    return {"asof":dt.date.today().isoformat(),"source":"SAMPLE (synthetic, illustrative) — replaced by the nightly job","calibration":cal,
            "indices":{"DOW":"Dow Jones 30","NDX":"Nasdaq-100","SPX":"S&P 500","RUT":"Russell 2000"},"sectors":SECTORS,"factors":FACTORS,"macrof":["MKT"]+MFAC,
            "names":names,"sectorCorr":{"order":osec,"m":M},"factorCov":_fcov}

# ---------- real fetch (nightly Action only; needs network) ------------------------------------
SECMAP={"Information Technology":"Technology","Technology":"Technology","Financials":"Financials",
        "Health Care":"Health Care","Consumer Discretionary":"Consumer Disc.","Communication":"Communication",
        "Communication Services":"Communication","Industrials":"Industrials","Consumer Staples":"Consumer Staples",
        "Energy":"Energy","Utilities":"Utilities","Materials":"Materials","Real Estate":"Real Estate"}

def fetch_russell(yf, limit, UA):
    """Russell 2000 constituents from the iShares IWM daily holdings CSV, batch-downloaded
    via yfinance (one request per 100 tickers). Returns names tagged idx=["RUT"]. Best-effort:
    chunks that fail are skipped so a partial universe still publishes."""
    import requests, csv, io
    IWM="https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund&asOfDate="
    t=requests.get(IWM,timeout=60,headers=UA).text
    rows=list(csv.reader(io.StringIO(t)))
    hdr=None
    for i,r in enumerate(rows):
        if "Ticker" in r and "Sector" in r: hdr=i; break
    if hdr is None: return []
    H=rows[hdr]; ci=H.index("Ticker"); ni=H.index("Name"); si=H.index("Sector")
    mi=H.index("Market Value") if "Market Value" in H else -1
    cons=[]
    for r in rows[hdr+1:]:
        if len(r)<=max(ci,ni,si): continue
        tk=r[ci].strip().upper().replace(".","-")        # yfinance class-share convention
        if not tk or not tk[0].isalpha() or len(tk)>5: continue
        sec=SECMAP.get(r[si].strip())
        if not sec: continue
        mv=0.0
        if mi>=0:
            try: mv=float(r[mi].replace(",","").replace("$","") or 0)
            except Exception: mv=0.0
        cons.append((tk, (r[ni].strip()[:24] or tk), sec, mv))
    if limit: cons=cons[:limit]
    out=[]
    for k in range(0,len(cons),100):
        ch=cons[k:k+100]; syms=[c[0] for c in ch]
        try:
            data=yf.download(syms, period="1y", interval="1d", auto_adjust=True,
                             group_by="ticker", threads=True, progress=False)
        except Exception as e:
            sys.stderr.write(f"russell chunk fail @ {k}: {e}\n"); continue
        for tk,nm,sec,mv in ch:
            try:
                sub=data[tk] if len(syms)>1 else data
                cl=[];vo=[];hi=[];lo=[]
                for c,v,H,Lw in zip(sub["Close"].tolist(), sub["Volume"].tolist(), sub["High"].tolist(), sub["Low"].tolist()):
                    c=float(c); v=float(v)
                    if c==c and c>0:
                        cl.append(c); vo.append(v if v==v else 0.0)
                        H=float(H); Lw=float(Lw); hi.append(H if H==H else c); lo.append(Lw if Lw==Lw else c)
                if len(cl)<30: continue
                wk=cl[::5]; wr=[(wk[i]/wk[i-1]-1) for i in range(1,len(wk)) if wk[i-1]]
                out.append({"t":tk,"n":nm,"sec":sec,"idx":["RUT"],"mcap":round(mv or 1e9),
                            "wr":[round(x,5) for x in wr],"_cl":cl,"_hi":hi,"_lo":lo,"_vol":vo,"_fcf":None})
            except Exception: continue
    return out

def fred_series_weekly(key, sid):
    """One FRED daily series -> weekly pct-change list (official, point-in-time-friendly)."""
    import requests
    try:
        r=requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id":sid,"api_key":key,"file_type":"json",
                    "observation_start":(dt.date.today()-dt.timedelta(days=400)).isoformat()},timeout=30)
        obs=r.json().get("observations",[])
        vals=[float(o["value"]) for o in obs if o.get("value") not in (".","",None)]
        w=vals[::5]; return [(w[i]/w[i-1]-1) for i in range(1,len(w)) if w[i-1]]
    except Exception: return []

def fred_macro(key):
    """Official macro panel from FRED (gated by FRED_API_KEY): broad-dollar, 10y, VIX, WTI."""
    m={"DXY":fred_series_weekly(key,"DTWEXBGS"),"RATE":fred_series_weekly(key,"DGS10"),
       "VIX":fred_series_weekly(key,"VIXCLS"),"OIL":fred_series_weekly(key,"DCOILWTICO")}
    return {k:v for k,v in m.items() if v}

def _earn_rec(e):
    """One quarter -> compact record for the chart: date(announce), actual/est EPS, surprise%, fiscal Q/Y."""
    a=e.get("epsActual"); es=e.get("epsEstimate"); s=None
    if a is not None and es not in (None,0):
        try: s=round(100.0*(a-es)/abs(es),1)
        except Exception: s=None
    return {"d":e.get("date"),"a":a,"e":es,"q":e.get("quarter"),"y":e.get("year"),"s":s}

def finnhub_beat(key, names, cap=60):
    """Finnhub EARNINGS CALENDAR (one call/ticker) -> BOTH:
      n['earn'] = {q:[last ~6 quarters: announce date + actual/est EPS + surprise%], next:{upcoming est}}
      n['_beat'] = Bayesian-shrunk historical beat-probability (folded into the odds ladder).
    The per-quarter dates+EPS drive the terminal's Q1-Q4 report-date vertical lines and the
    market-multiple (P/E) annotation; 'next' drives the 6-month expected-vs-actual view."""
    import requests, datetime as dt
    from ratelimit import Limiter
    lim=Limiter("finnhub")
    today=dt.date.today(); frm=(today-dt.timedelta(days=760)).isoformat(); to=(today+dt.timedelta(days=95)).isoformat()
    big=[n for n in names if "RUT" not in n.get("idx",[])][:cap]
    for n in big:
        if not lim.acquire(): break          # free-tier budget spent or breaker tripped
        try:
            r=requests.get("https://finnhub.io/api/v1/calendar/earnings",
                           params={"symbol":n["t"],"from":frm,"to":to,"token":key},timeout=15)
            if Limiter.is_limit(r.status_code, getattr(r,"text","")):
                lim.trip("finnhub %s"%r.status_code); break
            cal=(r.json() or {}).get("earningsCalendar") or []
            if not isinstance(cal,list) or not cal: continue
            cal.sort(key=lambda e:(e.get("date") or ""))
            past=[e for e in cal if e.get("epsActual") is not None]
            fut =[e for e in cal if e.get("epsActual") is None and (e.get("date") or "")>=today.isoformat()]
            tot=[e for e in past if e.get("epsEstimate") is not None]
            if tot:
                beats=[e for e in tot if (e.get("epsActual") or 0)>=(e.get("epsEstimate") or 0)]
                n["_beat"]=round((len(beats)+1.0)/(len(tot)+2.0),2)   # shrink toward 0.5
            earn={"q":[_earn_rec(e) for e in past[-6:]]}
            if fut: earn["next"]=_earn_rec(fut[0])
            if earn["q"] or earn.get("next"): n["earn"]=earn
        except Exception: continue

def twelvedata_ivol(key, names, cap=40):
    """Twelve Data 1h bars -> annualized INTRADAY realized vol (P3-18 family). Sets n['ivol']."""
    import requests
    from ratelimit import Limiter
    lim=Limiter("twelvedata")
    big=sorted([n for n in names if "RUT" not in n.get("idx",[])], key=lambda n:-n.get("mcap",0))[:cap]
    for n in big:
        if not lim.acquire(): break          # 8/min free tier -> throttle + budget + breaker
        try:
            r=requests.get("https://api.twelvedata.com/time_series",
                params={"symbol":n["t"],"interval":"1h","outputsize":"200","apikey":key},timeout=15)
            _body=r.json()
            if Limiter.is_limit(r.status_code, str(_body)):
                lim.trip("twelvedata limit"); break
            v=_body.get("values",[])
            cl=[float(x["close"]) for x in v if x.get("close")][::-1]
            if len(cl)<30: continue
            rr=[math.log(cl[i]/cl[i-1]) for i in range(1,len(cl)) if cl[i-1]>0 and cl[i]>0]
            if len(rr)<10: continue
            mu=sum(rr)/len(rr); sd=(sum((x-mu)**2 for x in rr)/(len(rr)-1))**0.5
            n["ivol"]=round(sd*math.sqrt(252*6.5)*100,1)
        except Exception: continue

# ---- FREE SEC Form 4 insider engine (no paid tier): separates discretionary buys/sells (SIGNAL) from 10b5-1 planned sales (NOISE) ----
_INS_UA={"User-Agent":"MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}
_INS_PLAN=re.compile(r"10b5[\-\u2010\u2011\u2012\u2013\u2014]?\s*1|rule\s*10b5", re.I)
_INS_CIK=None
_INS_CIK_FAILS=[0]                 # bounded retry on the bulk CIK map (avoid re-pulling 8MB forever)
_SEC_MIN_INTERVAL=0.16            # ~6 req/s \u2014 under SEC's 10 req/s fair-access ceiling
_sec_last=[0.0]
def _sec_get(s, url, tries=4):
    """Throttled SEC GET: one global pacer for EVERY edgar/data.sec call (bulk CIK, submissions,
    Form 4 docs), with exponential backoff + Retry-After on 403/429/5xx. Returns Response or None.
    A clean 0/N insider coverage was a rate-limit cascade: bursts >10/s tripped 403 on every call."""
    import time as _t
    for k in range(tries):
        gap=_t.time()-_sec_last[0]
        if gap<_SEC_MIN_INTERVAL: _t.sleep(_SEC_MIN_INTERVAL-gap)
        _sec_last[0]=_t.time()
        try:
            r=s.get(url, headers=_INS_UA, timeout=25)
        except Exception:
            _t.sleep(0.5*(k+1)); continue
        if r.status_code==200: return r
        if r.status_code in (403,429,500,502,503,504):
            ra=str(r.headers.get("Retry-After",""))
            wait=float(ra) if ra[:6].isdigit() and ra.strip() else 0.8*(2**k)
            _t.sleep(min(wait,8.0)); continue
        return r                  # 404 / other \u2014 hand back so caller can skip cleanly
    return None
def _load_cik(s):
    """Load (once) the SEC ticker->CIK map. Resilient: bounded retries, and one failure no longer
    cascades the whole universe to None."""
    global _INS_CIK
    if _INS_CIK is not None: return _INS_CIK
    if _INS_CIK_FAILS[0]>=6: return None
    r=_sec_get(s,"https://www.sec.gov/files/company_tickers.json")
    if r is None or r.status_code!=200:
        _INS_CIK_FAILS[0]+=1; return None
    try:
        j=r.json(); _INS_CIK={v["ticker"].upper():str(v["cik_str"]).zfill(10) for v in j.values()}
        return _INS_CIK
    except Exception:
        _INS_CIK_FAILS[0]+=1; return None
_SEC_FISCAL_CACHE={}
def _sec_fiscal_map(ticker, s):
    """AUTHORITATIVE fiscal-period focus from SEC EDGAR companyfacts -> {periodEndISO:{fp(1-4),fy,filed}}.
    The XBRL facts carry fy / fp / end / filed per 10-Q (Q1-Q3) and 10-K (FY->Q4). Used to cross-check
    and, when FMP is sparse, supply the correct fiscal label. Returns {} on any failure (fail-soft)."""
    if ticker in _SEC_FISCAL_CACHE: return _SEC_FISCAL_CACHE[ticker]
    out={}
    try:
        cikmap=_load_cik(s); cik=cikmap.get(ticker.upper()) if cikmap else None
        if not cik:
            _SEC_FISCAL_CACHE[ticker]={}; return {}
        r=_sec_get(s,"https://data.sec.gov/api/xbrl/companyfacts/CIK%s.json"%cik)
        if r is None or r.status_code!=200:
            _SEC_FISCAL_CACHE[ticker]={}; return {}
        facts=(r.json().get("facts") or {}).get("us-gaap") or {}
        concept=None
        for c in ("EarningsPerShareDiluted","EarningsPerShareBasic","Revenues",
                  "RevenueFromContractWithCustomerExcludingAssessedTax","NetIncomeLoss"):
            if c in facts: concept=c; break
        if not concept:
            _SEC_FISCAL_CACHE[ticker]={}; return {}
        for _u,arr in (facts[concept].get("units") or {}).items():
            for d in arr:
                if d.get("form") not in ("10-Q","10-K"): continue
                fp=d.get("fp"); end=d.get("end"); fy=d.get("fy"); filed=d.get("filed")
                if not (fp and end and fy and filed): continue
                q=4 if fp in ("FY","Q4") else (int(fp[1]) if fp[:1]=="Q" and fp[1:2].isdigit() else None)
                if q is None: continue
                key=str(end)[:10]; rec=out.get(key)
                if (not rec) or str(filed)>rec["filed"]:          # keep latest filing per period (amendments)
                    out[key]={"fp":q,"fy":int(fy),"filed":str(filed)[:10]}
    except Exception:
        out={}
    _SEC_FISCAL_CACHE[ticker]=out; return out
def _form4_xml_url(s, cik_int, acc_nodash, primary):
    """Resolve the RAW Form 4 ownership XML. primaryDocument is often the XSL-rendered path
    (e.g. 'xslF345X05/wk-form4_..xml') which returns HTML, not parseable XML \u2014 strip the xsl
    dir. If primaryDocument isn't .xml at all (older .txt filings), read the accession's
    index.json directory and pick the real ownership .xml."""
    base="https://www.sec.gov/Archives/edgar/data/%s/%s/"%(cik_int,acc_nodash)
    if primary and primary.lower().endswith(".xml"):
        return base+re.sub(r"^xsl[^/]*/","",primary)
    r=_sec_get(s, base+"index.json")
    if r is not None and r.status_code==200:
        try:
            items=r.json().get("directory",{}).get("item",[])
            xmls=[it.get("name","") for it in items if it.get("name","").lower().endswith(".xml")]
            cand=[x for x in xmls if not x.lower().startswith("xsl")] or xmls
            for x in cand:
                if re.search(r"form4|ownership|f345|doc4|wf-?form4|wk-?form4", x, re.I): return base+x
            if cand: return base+cand[0]
        except Exception: pass
    return None
def _ins_g(node,path):
    el=node.find(path); return (el.text or "").strip() if (el is not None and el.text) else ""
def _ins_num(x):
    try: return float(str(x).replace(",",""))
    except Exception: return None
def parse_form4(xml_bytes):
    try: root=ET.fromstring(xml_bytes)
    except Exception: return []
    notes={fn.get("id",""):(fn.text or "") for fn in root.findall(".//footnotes/footnote")}
    name=_ins_g(root,".//reportingOwner/reportingOwnerId/rptOwnerName")
    rel=root.find(".//reportingOwner/reportingOwnerRelationship"); role=""
    if rel is not None:
        if _ins_g(rel,"isDirector") in ("1","true"): role="Director"
        if _ins_g(rel,"isOfficer") in ("1","true"): role=_ins_g(rel,"officerTitle") or "Officer"
        if _ins_g(rel,"isTenPercentOwner") in ("1","true"): role=role or "10% owner"
    out=[]
    for t in root.findall(".//nonDerivativeTransaction"):
        code=_ins_g(t,"transactionCoding/transactionCode"); ad=_ins_g(t,"transactionAmounts/transactionAcquiredDisposedCode/value")
        sh=_ins_num(_ins_g(t,"transactionAmounts/transactionShares/value")); px=_ins_num(_ins_g(t,"transactionAmounts/transactionPricePerShare/value"))
        date=_ins_g(t,"transactionDate/value"); planned=False
        for fr in t.findall(".//footnoteId"):
            if _INS_PLAN.search(notes.get(fr.get("id",""),"")): planned=True
        out.append({"name":name,"role":role,"date":date,"code":code,"ad":ad,"shares":sh,"price":px,
                    "value":(sh*px if (sh and px) else None),"planned":planned})
    return out
def insider_signal(txns, days=120, asof=None):
    asof=asof or dt.date.today(); cut=asof-dt.timedelta(days=days)
    def rec(t):
        try: return dt.date.fromisoformat(t["date"])>=cut
        except Exception: return False
    R=[t for t in txns if rec(t)]
    buy=sum(t["value"] or 0 for t in R if t["code"]=="P" and t["ad"]=="A")
    disc=sum(t["value"] or 0 for t in R if t["code"]=="S" and t["ad"]=="D" and not t["planned"])
    plan=sum(t["value"] or 0 for t in R if t["code"]=="S" and t["ad"]=="D" and t["planned"])
    nb=len({t["name"] for t in R if t["code"]=="P" and t["ad"]=="A"}); ns=len({t["name"] for t in R if t["code"]=="S" and t["ad"]=="D" and not t["planned"]})
    gross=buy+disc; net=buy-disc; score=(net/gross) if gross>0 else 0.0
    if buy>0 and net>0: v="insider buying (signal)"
    elif disc>0 and net<0: v="discretionary selling (caution)"
    elif plan>0 and disc==0 and buy==0: v="routine 10b5-1 selling (noise)"
    else: v="quiet"
    return {"days":days,"buy":round(buy),"discSell":round(disc),"planSell":round(plan),"buyers":nb,"sellers":ns,"score":round(score,2),"verdict":v}
def fetch_insider(ticker, max_filings=15, sess=None):
    try:
        import requests
        s=sess or requests.Session()
        cikmap=_load_cik(s)
        if not cikmap: return None
        cik=cikmap.get(ticker.upper())
        if not cik: return None
        rsub=_sec_get(s,"https://data.sec.gov/submissions/CIK%s.json"%cik)
        if rsub is None or rsub.status_code!=200: return None
        sub=rsub.json()
        r=sub.get("filings",{}).get("recent",{}); forms=r.get("form",[]); acc=r.get("accessionNumber",[]); pdoc=r.get("primaryDocument",[])
        txns=[]; got=0; ci=str(int(cik))
        for i in range(len(forms)):
            if forms[i]!="4": continue
            doc=pdoc[i] if i<len(pdoc) else ""
            url=_form4_xml_url(s, ci, acc[i].replace("-",""), doc)
            if not url:
                got+=1
                if got>=max_filings: break
                continue
            rb=_sec_get(s, url)
            if rb is not None and rb.status_code==200:
                body=rb.content
                if b"ownershipDocument" in body: txns+=parse_form4(body)
            got+=1
            if got>=max_filings: break
        return insider_signal(txns) if txns else None
    except Exception: return None

def load_institutional():
    """Read the committed institutional.json (written quarterly by build_institutional.py from free SEC 13F data sets)."""
    for pth in ("institutional.json","../institutional.json","../../institutional.json","tools/market_map/institutional.json"):
        try:
            with open(pth) as f: return json.load(f)
        except Exception: continue
    return {}

def real_universe():
    import requests
    UA={"User-Agent":"MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}
    # constituents from index ETF holdings (free daily CSVs); fall back to the SEED symbols
    def holdings(url, sym_col="Ticker"):
        try:
            t=requests.get(url,timeout=30,headers=UA).text
            import csv,io
            rows=list(csv.reader(io.StringIO(t)))
            hdr=None
            for i,r in enumerate(rows):
                if sym_col in r: hdr=i; break
            if hdr is None: return []
            ci=rows[hdr].index(sym_col)
            out=[]
            for r in rows[hdr+1:]:
                if len(r)>ci and r[ci].strip() and r[ci].strip().isalpha(): out.append(r[ci].strip().upper())
            return out
        except Exception: return []
    spx=set(holdings("https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"))  # may need xlsx parse; best-effort
    # Robust fallback: SEED membership defines the universe if holdings fetch is unavailable.
    names=[]
    # ---- DATA-SOURCE HIERARCHY: FMP Ultimate (paid) is PRIMARY for all prices; yfinance is a
    #      labeled BACKUP, switchable off via env MRKT_YF_ENABLED=0. When FMP fails for a symbol
    #      and yfinance is ON, we fall back (and record it); when yfinance is OFF, FMP-only. The
    #      health tracker (PH) records per-source counts + the last successful FMP pull timestamp
    #      so the terminal can show "FMP Ultimate not pulling as of <ts>". ----
    import time as _time
    import fmp_history as _fmph
    try: import data_quality as _dq
    except Exception: _dq=None
    import requests as _rqp
    _PSESS=_rqp.Session(); _PSESS.headers.update({"User-Agent":UA})
    YF_ON=(os.environ.get("MRKT_YF_ENABLED","1").strip().lower() not in ("0","false","off","no"))
    yf=None
    if YF_ON:
        try:
            import yfinance as yf
        except Exception as _yfe:
            sys.stderr.write("yfinance import failed (%s); running FMP-only\n"%_yfe); yf=None
    PH={"fmp":0,"yf":0,"miss":0,"fmpLastOk":None,"yfEnabled":bool(YF_ON),
        "yfImported":bool(yf is not None),"fmpKeyPresent":bool(_fmph.have_key())}
    def _now_utc():
        return _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
    def _get_hist(sym, min_rows=10):
        """Price getter — FMP Ultimate FIRST, yfinance FALLBACK (if enabled). dict(cl,hi,lo,vo,src) or None."""
        rows=None
        try: rows=_fmph.eod_ohlcv(sym, sess=_PSESS, min_rows=min_rows)
        except Exception: rows=None
        if rows:
            PH["fmp"]+=1; PH["fmpLastOk"]=_now_utc()
            return {"cl":[r[4] for r in rows],"hi":[r[2] for r in rows],"lo":[r[3] for r in rows],
                    "vo":[float(r[5]) for r in rows],"src":"fmp"}
        if yf is not None:
            try:
                h=yf.Ticker(sym).history(period="1y",interval="1d",auto_adjust=True)
                cl=[];vo=[];hi=[];lo=[]
                for c,v,H,Lw in zip(h["Close"].tolist(),h["Volume"].tolist(),h["High"].tolist(),h["Low"].tolist()):
                    c=float(c)
                    if c==c and c>0:
                        cl.append(c); vo.append(float(v) if v==v else 0.0)
                        H=float(H); Lw=float(Lw); hi.append(H if H==H else c); lo.append(Lw if Lw==Lw else c)
                if len(cl)>=min_rows:
                    PH["yf"]+=1
                    return {"cl":cl,"hi":hi,"lo":lo,"vo":vo,"src":"yfinance"}
            except Exception: pass
        PH["miss"]+=1
        return None
    try:
        from free_financial_data.sec_client import SecClient  # optional EDGAR client (vendored in private repo only)
        sec=SecClient()
    except Exception:
        sec=None   # not vendored in the public repo; SEC pulls below use the inline requests+UA path. 'sec' is unused.
    for sym,nm,sec_name,code in SEED:        # phase-1 universe (extend to full big-3 once holdings parse is wired)
        try:
            _ph=_get_hist(sym, min_rows=10)            # FMP Ultimate primary -> yfinance fallback
            if not _ph: raise ValueError("no price data (FMP+yfinance)")
            cl=_ph["cl"]; vo=_ph["vo"]; hi=_ph["hi"]; lo=_ph["lo"]
            wk=cl[::5]; wr=[(wk[i]/wk[i-1]-1) for i in range(1,len(wk)) if wk[i-1]]
            mcap=None; fcf=None
            valr={"pe":None,"fpe":None,"peg":None,"evb":None,"epsg":None,"revg":None}
            if yf is not None:                          # mcap + valuation SEED from yfinance info (FMP refreshes below)
                try:
                    info=yf.Ticker(sym).get_info(); mcap=float(info.get("marketCap") or 0) or (cl[-1]*float(info.get("sharesOutstanding") or 0))
                    fcf=info.get("freeCashflow")
                    def _fnum(x):
                        try: x=float(x); return x if (x==x and abs(x)<1e6) else None
                        except Exception: return None
                    valr={"pe":_fnum(info.get("trailingPE")),"fpe":_fnum(info.get("forwardPE")),
                          "peg":_fnum(info.get("trailingPegRatio") or info.get("pegRatio")),"evb":_fnum(info.get("enterpriseToEbitda")),
                          "epsg":_fnum(info.get("earningsGrowth")),"revg":_fnum(info.get("revenueGrowth"))}
                except Exception: pass
            names.append({"t":sym,"n":nm,"sec":sec_name,"idx":membership(code),"mcap":round(mcap or 1e9),
                          "wr":[round(x,5) for x in wr],"_cl":cl,"_hi":hi,"_lo":lo,"_vol":vo,"_fcf":float(fcf) if fcf else None,"_val":valr,"_psrc":_ph["src"]})
            try: names[-1]["insider"]=fetch_insider(sym, max_filings=15)
            except Exception: names[-1]["insider"]=None
            # DATA-QUALITY sentinel: flag skewed / stale / broken price series (does not drop — labels)
            if _dq is not None:
                try:
                    _h=_dq.series_health(cl, vo); names[-1]["_dq"]=_h["verdict"]
                    if _h["verdict"]!="clean": names[-1]["_dqr"]=_h["reasons"][:3]
                except Exception: pass
            # CROSS-SOURCE agreement (SAMPLED ~1/7 to bound API load): when FMP supplied the price, spot-check
            # a yfinance pull and flag provider disagreement (a skew between feeds = suspect data).
            if _dq is not None and _ph.get("src")=="fmp" and yf is not None and (len(names)%7==0):
                try:
                    _yh=yf.Ticker(sym).history(period="3mo",interval="1d",auto_adjust=True)
                    _yc=[float(x) for x in _yh["Close"].tolist() if float(x)==float(x) and float(x)>0]
                    if len(_yc)>=5:
                        _xa=_dq.cross_source_agree(cl, _yc)
                        names[-1]["xsrc"]={"agree":_xa.get("agree"),"dev":_xa.get("maxRelDev"),"n":_xa.get("n")}
                except Exception: pass
        except Exception as e:
            sys.stderr.write(f"skip {sym}: {e}\n")
    # ---- factor panel: lightweight closes for cross-asset conditioning (tagged idx=["FACTOR"]) ----
    _fok=0
    for fsym,fnm,fbucket in FACTOR_PANEL:
        try:
            _fph=_get_hist(fsym, min_rows=40)          # FMP-first; yfinance fallback for cross-asset proxies
            if not _fph: continue
            fcl=_fph["cl"]; fvo=_fph["vo"]
            if len(fcl)<40: continue
            fwk=fcl[::5]; fwr=[(fwk[i]/fwk[i-1]-1) for i in range(1,len(fwk)) if fwk[i-1]]
            names.append({"t":fsym,"n":fnm,"sec":fbucket,"idx":["FACTOR"],"mcap":0,
                          "wr":[round(x,5) for x in fwr],"_cl":fcl,"_hi":list(fcl),"_lo":list(fcl),"_vol":fvo,
                          "_fcf":None,"_val":{"pe":None,"fpe":None,"peg":None,"evb":None,"epsg":None,"revg":None},"insider":None,"factor":True})
            _fok+=1
        except Exception as fe:
            sys.stderr.write("factor skip %s: %s\n"%(fsym,fe))
    sys.stderr.write("factor panel: %d/%d proxies loaded\n"%(_fok,len(FACTOR_PANEL)))
    # ---- Russell 2000 (phase 2): iShares IWM holdings, batch-downloaded (env RUSSELL_LIMIT caps size; 0 = all) ----
    try:
        lim=int(os.environ.get("RUSSELL_LIMIT","2000")); lim=lim or None
        if yf is None:
            raise RuntimeError("Russell batch fetch needs yfinance (disabled via MRKT_YF_ENABLED=0); skipping")
        rus=fetch_russell(yf, lim, UA)
        sys.stderr.write(f"russell: fetched {len(rus)} constituents\n"); names+=rus
    except Exception as e:
        sys.stderr.write(f"russell skip: {e}\n")
    # market proxy = SPY weekly
    def _wret(sym):
        _wh=_get_hist(sym, min_rows=10)               # FMP-first; yfinance fallback for index/macro proxies
        if not _wh: return []
        c=_wh["cl"]; w=c[::5]; return [(w[i]/w[i-1]-1) for i in range(1,len(w)) if w[i-1]]
    mkt=_wret("SPY") or [0.0]*52
    ff={"SMB":[0.0]*len(mkt),"HML":[0.0]*len(mkt),"MOM":[0.0]*len(mkt)}  # FF factors optional; default 0 if no source
    # ---- macro factor panel (free proxies) for the sparse Lasso attribution + dislocation ----
    macro={"DXY":_wret("DX-Y.NYB") or _wret("UUP"),"RATE":_wret("^TNX"),
           "VIX":_wret("^VIX"),"OIL":_wret("CL=F") or _wret("USO")}
    # broader dependency factors (best-effort; missing ones just stay inactive)
    macro["HYG"]=_wret("HYG"); macro["GOLD"]=_wret("GC=F") or _wret("GLD")
    macro["COPPER"]=_wret("HG=F") or _wret("CPER"); macro["NATGAS"]=_wret("NG=F") or _wret("UNG")
    _t10=_wret("^TNX"); _sh=_wret("^IRX")               # 2s10s steepness proxy = d(10y) - d(13wk)
    if _t10 and _sh:
        _L=min(len(_t10),len(_sh)); macro["SLOPE"]=[_t10[-_L:][i]-_sh[-_L:][i] for i in range(_L)]
    macro={k:(v if len(v)==len(mkt) else (v[-len(mkt):] if len(v)>len(mkt) else v+[0.0]*(len(mkt)-len(v)))) for k,v in macro.items() if v}
    # ---- optional FREE connectors (gated by repo-secret keys; degrade gracefully when unset) ----
    fk=os.environ.get("FRED_API_KEY","").strip()
    if fk:
        try:
            fm=fred_macro(fk)
            for k,v in fm.items():
                macro[k]=(v if len(v)==len(mkt) else (v[-len(mkt):] if len(v)>len(mkt) else v+[0.0]*(len(mkt)-len(v))))
            sys.stderr.write(f"FRED macro: {len(fm)} official series\n")
        except Exception as e: sys.stderr.write(f"FRED skip: {e}\n")
    # ---- FMP Ultimate: REAL Treasury curve + commodity history (paid; PRIMARY over free proxies) ----
    #      Replaces the ETF/yfinance proxies for RATE / 2s10s SLOPE / OIL / GOLD / COPPER / NATGAS /
    #      SILVER etc. with genuine FMP histories, and stashes the raw curve+commodity series (labeled)
    #      for the macroSeries output block. yfinance/FRED remain as the labeled fallback for any gap.
    try:
        import fmp_history as _fmph
        if _fmph.have_key():
            _mm=_fmph.macro_from_fmp()
            if _mm and _mm.get("macro"):
                _al=lambda v:(v if len(v)==len(mkt) else (v[-len(mkt):] if len(v)>len(mkt) else v+[0.0]*(len(mkt)-len(v))))
                _src=globals().setdefault("_MACRO_SRC",{})
                for k,v in _mm["macro"].items():
                    if v: macro[k]=_al(v); _src[k]="FMP Ultimate"
                _cur=(_mm.get("series") or {}).get("treasury") or {}
                if _cur.get("series"):                      # trim to recent points so marketmap.json stays lean
                    _cur=dict(_cur); _cur["series"]={lab:ser[-130:] for lab,ser in _cur["series"].items()}
                    _cur["slope2s10s"]=(_cur.get("slope2s10s") or [])[-130:]
                _ckeys=(_mm.get("series") or {}).get("commodityKeys") or {}
                globals()["_COMMODITY_LABELS"]=_ckeys           # label->name; build() wires ALL of these into attribution
                globals()["_MACRO_SERIES"]={"source":"FMP Ultimate","asof":_cur.get("asof"),
                                            "treasury":_cur,"commodities":(_mm.get("series") or {}).get("commodities"),
                                            "commodityKeys":_ckeys,"drivers":sorted(_mm["macro"].keys())}
                sys.stderr.write("FMP Ultimate macro: %d real driver series (%s)\n"%(len(_mm["macro"]),", ".join(sorted(_mm["macro"].keys()))))
    except Exception as _e:
        sys.stderr.write("FMP history skip: %s\n"%str(_e)[:140])
    # EARNINGS CALENDAR — FMP Ultimate is the PRIMARY source now (report dates + EPS actual/est +
    # surprise + the next date), driving the terminal's 5 quarterly report-date lines. Finnhub (below)
    # is demoted to a gap-filler for any name FMP didn't return, and only when its key is present.
    try:
        import fmp_history as _fmpe
        if _fmpe.have_key():
            import requests as _rq
            _esess=_rq.Session(); _ne=0; _nq=0; _SEC_BUDGET=[200]; _secfix=0
            for n in [x for x in names if "RUT" not in x.get("idx",[])]:
                try: ec=_fmpe.earnings_calendar(n["t"], sess=_esess)
                except Exception: ec=None
                if not ec: continue
                earn={"q":ec.get("q") or []}
                if ec.get("next"): earn["next"]=ec["next"]
                if ec.get("fyEnd") is not None: earn["fyEnd"]=ec["fyEnd"]        # fiscal-year-end month
                if ec.get("qMonths"): earn["qMonths"]=ec["qMonths"]             # company report-month cadence
                # SEC EDGAR companyfacts cross-check/fallback for fiscal LABELS (authoritative fp/fy).
                # Targeted at quarters whose label is NOT from the income statement (sparse/calendar),
                # bounded by a per-run companyfacts budget so bandwidth stays sane.
                try:
                    _needsec=bool(earn["q"]) and any((qq.get("labelSrc")!="is" or qq.get("y") is None) for qq in earn["q"])
                    if _needsec and _SEC_BUDGET[0]>0:
                        _SEC_BUDGET[0]-=1; sf=_sec_fiscal_map(n["t"], _esess)
                        for qq in earn["q"]:
                            best=None; bd=9
                            for _pe,_rec in sf.items():
                                try: ddx=abs((dt.date.fromisoformat(qq["d"])-dt.date.fromisoformat(_rec["filed"])).days)
                                except Exception: ddx=9
                                if ddx<bd: bd=ddx; best=_rec
                            if best and bd<=5:
                                qq["q"]=best["fp"]; qq["y"]=best["fy"]; qq["labelSrc"]="sec"; qq["conf"]=True; _secfix+=1
                except Exception: pass
                if earn["q"] or earn.get("next"):
                    n["earn"]=earn; n["_earnSrc"]="FMP Ultimate"; _ne+=1; _nq+=len(earn["q"])
                if ec.get("beat") is not None: n["_beat"]=ec["beat"]
            sys.stderr.write("SEC fiscal cross-check: %d labels corrected (budget left %d)\n"%(_secfix,_SEC_BUDGET[0]))
            sys.stderr.write("FMP Ultimate earnings: %d names, %d quarters (primary)\n"%(_ne,_nq))
    except Exception as _e:
        sys.stderr.write("FMP earnings skip: %s\n"%str(_e)[:140])
    ek=os.environ.get("FINNHUB_API_KEY","").strip()
    if ek:
        _gap=[n for n in names if not n.get("earn")]      # FMP is primary; Finnhub fills only the gaps
        try: finnhub_beat(ek, _gap); sys.stderr.write("Finnhub estimates: gap-fill %d names\n"%len(_gap))
        except Exception as e: sys.stderr.write(f"Finnhub skip: {e}\n")
    tk=os.environ.get("TWELVEDATA_API_KEY","").strip()
    if tk:
        try: twelvedata_ivol(tk, names); sys.stderr.write("Twelve Data: intraday vol set\n")
        except Exception as e: sys.stderr.write(f"TwelveData skip: {e}\n")
    # ---- options walls (gamma) for the most liquid names only (capped; OPT_LIMIT, default 40) ----
    def fetch_opt(sym, spot):
        try:
            tk=yf.Ticker(sym); exps=tk.options
            if not exps: return None
            ch=tk.option_chain(exps[0])
            def wall(df):
                best=None; bo=-1.0
                for k,oi in zip(df["strike"].tolist(), df["openInterest"].tolist()):
                    oi=float(oi) if oi==oi else 0.0
                    if oi>bo: bo=oi; best=float(k)
                return best
            cw=wall(ch.calls); pw=wall(ch.puts)
            tc=sum(float(x) if x==x else 0 for x in ch.calls["openInterest"].tolist())
            tp=sum(float(x) if x==x else 0 for x in ch.puts["openInterest"].tolist())
            pcr=round(tp/tc,2) if tc>0 else None
            gex=round((pw+cw)/2.0,2) if (pw and cw) else None
            return {"pw":round(pw,2) if pw else None,"cw":round(cw,2) if cw else None,"pcr":pcr,"gex":gex}
        except Exception: return None
    try:
        optlim=int(os.environ.get("OPT_LIMIT","40"))
        big=sorted([n for n in names if "RUT" not in n["idx"] and n.get("_cl")], key=lambda n:-n["mcap"])
        for n in big[:optlim]:
            n["_opt"]=fetch_opt(n["t"], n["_cl"][-1])
    except Exception as e:
        sys.stderr.write(f"opt skip: {e}\n")
    inst=load_institutional()
    for n in names:
        if not n.get("inst"): n["inst"]=inst.get(n["t"])
    # ---- optional enrichment: free FTD squeeze always; FMP valuation + EODHD gamma when keys set ----
    try:
        if _sqz:
            _sq=_sqz.fetch_squeeze([n["t"] for n in names])
            for n in names:
                if _sq.get(n["t"]): n["short"]=_sq[n["t"]]
    except Exception: pass
    # ---- enrichment with PER-SOURCE OBSERVABILITY (no silent swallow): a dead/wrong-tier key
    #      must look DIFFERENT from a working one. We count usable results per source, emit loud
    #      CI ::warning:: lines, and stash a dataHealth block into the published JSON. ----
    import sys as _sys, os as _os
    _gcap=0; _fmp_try=_fmp_ok=_fmp_err=0; _eod_try=_eod_ok=_eod_err=0; _alp_ok=0; _errs=[]
    _earn_ok=_dcf_ok=_ptgt_ok=_est_ok=0; _fmp_lim=None
    _EST_HIST=_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),"est_history.jsonl")   # accumulating consensus snapshots (committed)
    _TODAY_ISO=__import__("datetime").date.today().isoformat()
    try:
        from ratelimit import Limiter as _Lim; _fmp_lim=_Lim("fmp")   # shared budget across valuation + premium pulls
    except Exception: _fmp_lim=None
    _VALFIELDS=("pe","fpe","peg","evb","epsg","revg")
    # FAIL-FAST: one classified probe call instead of hammering 150+ tickers with a dead key.
    _fmp_probe={"ok":bool(_fmp),"reason":"ok","message":""}
    if _fmp and hasattr(_fmp,"probe_key"):
        try: _fmp_probe=_fmp.probe_key()
        except Exception as _pe: _fmp_probe={"ok":False,"reason":"probe_error","message":str(_pe)[:120]}
    _fmp_live=bool(_fmp) and bool(_fmp_probe.get("ok"))
    if _fmp and not _fmp_live:
        _sys.stderr.write("FMP probe: key NOT usable (%s) - %s - skipping per-ticker valuation enrichment\n"%(_fmp_probe.get("reason"),_fmp_probe.get("message")))
    for n in names:
        if _fmp_live:
            _fmp_try+=1
            try:
                fv=_fmp.fetch(n["t"])
                vv=fv.get("val") if fv else None
                # "val present" != "val populated": require >=1 real numeric field, else it's an empty shell
                if vv and any(vv.get(k) is not None for k in _VALFIELDS):
                    cur=dict(n.get("_val") or {})                 # start from yfinance valuation
                    for _vk in _VALFIELDS:                        # FMP fills/refreshes; keep yfinance where FMP is null
                        if vv.get(_vk) is not None: cur[_vk]=vv[_vk]
                    n["_val"]=cur; _fmp_ok+=1
            except Exception as e:
                _fmp_err+=1
                if len(_errs)<4: _errs.append("FMP %s: %s"%(n["t"], str(e)[:80]))
            # FMP Ultimate PREMIUM (equities only): earnings calendar + DCF intrinsic value + analyst price target
            if "FACTOR" not in n.get("idx",[]) and n.get("mcap") and hasattr(_fmp,"fetch_premium"):
                try:
                    _px=_fmp.fetch_premium(n["t"], lim=_fmp_lim)
                    if _px.get("earn"): n["earn"]=_px["earn"]; _earn_ok+=1
                    if _px.get("dcf") is not None: n["dcf"]=_px["dcf"]; _dcf_ok+=1
                    if _px.get("ptgt"): n["ptgt"]=_px["ptgt"]; _ptgt_ok+=1
                    if _px.get("est"):                               # forward consensus + accumulate revision history
                        _ec=_px["est"]
                        try:
                            _es.record(_EST_HIST, n["t"], _TODAY_ISO, str(_ec.get("period") or ""), _ec.get("eps"), _ec.get("n"))
                            _lastrep=None
                            if n.get("earn") and n["earn"].get("q"):
                                _qd=[x.get("d") for x in n["earn"]["q"] if x.get("d")]
                                if _qd: _lastrep=max(_qd)
                            _rev=_es.revision(_EST_HIST, n["t"], _lastrep, str(_ec.get("period") or "")) if _lastrep else None
                            n.setdefault("earn",{})["estCons"]={"eps":_ec.get("eps"),"period":_ec.get("period"),"n":_ec.get("n"),"rev":_ec.get("rev")}
                            if _rev: n["earn"]["estRev"]=_rev          # consensus drift since the last print (negative=cut, positive=raise)
                            _est_ok+=1
                        except Exception: pass
                except Exception: pass
                # derived premium signals — ONE source of truth reused by card/chart/map/scatter
                _lastpx=(n.get("_cl") or [None])[-1]
                if _lastpx:
                    if n.get("dcf"): n["dcfGap"]=round((_lastpx-n["dcf"])/n["dcf"],4)      # +above / -below intrinsic
                    _pt=n.get("ptgt") or {}
                    if _pt.get("tgt"): n["tgtUpside"]=round((_pt["tgt"]-_lastpx)/_lastpx,4) # +upside to consensus
        sp=(n.get("_cl") or [None])[-1]
        if _eod and sp and _gcap<140:
            _eod_try+=1
            try:
                ox=_eod.enrich_options(n["t"], sp, n.get("_cl"))   # GEX + Black-Scholes fair value/greeks/richness
                if ox:
                    if ox.get("gex"): n["gex"]=ox["gex"]; _eod_ok+=1
                    if ox.get("bs"):  n["bs"]=ox["bs"]             # BS option valuation vs same-ticker spot/RV
            except Exception as e:
                _eod_err+=1
                if len(_errs)<8: _errs.append("EODHD %s: %s"%(n["t"], str(e)[:80]))
            _gcap+=1
        if _alp and sp and not n.get("bs") and _gcap<140:          # free Alpaca fallback when EODHD has no options add-on
            try:
                ax=_alp.enrich_options(n["t"], sp, n.get("_cl"))     # IV+greeks+BS richness (GEX only if OI present)
                if ax:
                    if ax.get("bs"): n["bs"]=ax["bs"]; _alp_ok+=1
                    if ax.get("gex") and not n.get("gex"): n["gex"]=ax["gex"]
            except Exception as e:
                if len(_errs)<8: _errs.append("ALPACA %s: %s"%(n["t"], str(e)[:80]))
            _gcap+=1
    _kf=bool(_os.environ.get("FMP_API_KEY","").strip()); _ke=bool(_os.environ.get("EODHD_API_KEY","").strip())
    _ka=bool(_os.environ.get("ALPACA_API_KEY_ID","").strip() and _os.environ.get("ALPACA_API_SECRET_KEY","").strip())
    _sys.stderr.write("ENRICH: FMP key=%s tried=%d ok=%d err=%d | EODHD key=%s tried=%d gex=%d err=%d | ALPACA key=%s bs=%d\n"%(_kf,_fmp_try,_fmp_ok,_fmp_err,_ke,_eod_try,_eod_ok,_eod_err,_ka,_alp_ok))
    _sys.stderr.write("FMP PREMIUM: earnings=%d dcf=%d priceTarget=%d estConsensus=%d (Ultimate)\n"%(_earn_ok,_dcf_ok,_ptgt_ok,_est_ok))
    for _e in _errs: _sys.stderr.write("  - %s\n"%_e)
    if _kf and not _fmp_live:
        _r=_fmp_probe.get("reason"); _m=_fmp_probe.get("message") or ""
        if _r=="invalid_key":
            _sys.stderr.write("::warning::FMP_API_KEY is INVALID - FMP says: %s | FIX: replace the FMP_API_KEY secret with a key that passes /stable/quote?symbol=AAPL\n"%_m)
        elif _r=="rate_limited":
            _sys.stderr.write("::warning::FMP rate/bandwidth limit: %s | valuations skipped this run, auto-retries next run\n"%_m)
        elif _r=="plan_or_endpoint":
            _sys.stderr.write("::warning::FMP plan/endpoint issue: %s | /stable quote+ratios-ttm+analyst-estimates may not be in your tier\n"%_m)
        elif _r=="missing":
            _sys.stderr.write("::notice::FMP_API_KEY not set - valuation layer disabled\n")
        else:
            _sys.stderr.write("::warning::FMP key probe failed (%s): %s\n"%(_r,_m))
    elif _kf and _fmp_try and _fmp_ok==0:
        _sys.stderr.write("::warning::FMP key validated but parsed 0 usable valuations across %d tickers - likely a /stable field/endpoint change in parse_val\n"%_fmp_try)
    if _ke and _eod_try and _eod_ok==0:
        _sys.stderr.write("::warning::EODHD_API_KEY is SET but returned 0 option chains across %d tickers - the UnicornBay options add-on is likely not subscribed (402/403)\n"%_eod_try)
    # ---- PER-SOURCE COMPLETENESS (derived from the actual records) so EVERY pull is observable,
    #      not just FMP/EODHD. A silently-empty layer now shows up as 0/N in dataHealth and warns. ----
    def _cnt(pred):
        c=0
        for n in names:
            try:
                if pred(n): c+=1
            except Exception: pass
        return c
    _cov={"universe":len(names),
          "priceOk":_cnt(lambda n:bool(n.get("_cl"))),          # daily closes — FMP Ultimate primary, yfinance backup
          "mcapOk":_cnt(lambda n:bool(n.get("mcap"))),          # market cap (FMP/yfinance info)
          "instOk":_cnt(lambda n:bool(n.get("inst"))),          # SEC 13F institutional
          "insiderOk":_cnt(lambda n:bool(n.get("insider"))),    # SEC insider transactions
          "shortOk":_cnt(lambda n:bool(n.get("short"))),        # SEC short/FTD
          "ivolOk":_cnt(lambda n:n.get("ivol") is not None),    # TwelveData intraday implied vol
          "beatOk":_cnt(lambda n:n.get("_beat") is not None),   # Finnhub earnings-beat probability
          "valOk":_cnt(lambda n:bool(n.get("_val")) and any(n["_val"].get(k) is not None for k in ("pe","fpe","peg","evb"))),  # TRUE valuation coverage (yfinance + FMP)
          "earnOk":_earn_ok, "dcfOk":_dcf_ok, "ptgtOk":_ptgt_ok}  # FMP Ultimate premium: earnings calendar, DCF, price target
    for _k,_lbl in (("priceOk","yfinance daily closes"),("mcapOk","yfinance market caps"),
                    ("instOk","SEC 13F institutional"),("insiderOk","SEC insider"),("shortOk","SEC short/FTD")):
        if _cov[_k]==0:
            _sys.stderr.write("::warning::%s pull returned 0/%d - source down or throttled\n"%(_lbl,len(names)))
    _dqv={"clean":0,"degraded":0,"reject":0,"unknown":0,"flagged":[],"xsrcChecked":0,"xsrcDisagree":0}  # data-quality census
    for _n in names:
        _v=_n.get("_dq") or "unknown"
        _dqv[_v]=_dqv.get(_v,0)+1
        _xs=_n.get("xsrc")
        if _xs and _xs.get("agree") is not None:
            _dqv["xsrcChecked"]+=1
            if _xs.get("agree") is False: _dqv["xsrcDisagree"]+=1
        if _v in ("degraded","reject") and len(_dqv["flagged"])<30:
            _dqv["flagged"].append({"t":_n.get("t"),"v":_v,"why":_n.get("_dqr")})
    globals()["_DATA_HEALTH"]={"asof":dt.date.today().isoformat(),
        "dataQuality":_dqv,
        "fmpKey":_kf,"fmpKeyValid":bool(_fmp_live),"fmpKeyReason":_fmp_probe.get("reason"),"fmpKeyMessage":(_fmp_probe.get("message") or "")[:160],
        "fmpTried":_fmp_try,"fmpOk":_fmp_ok,"fmpErr":_fmp_err,
        "eodKey":_ke,"eodTried":_eod_try,"eodOk":_eod_ok,"eodErr":_eod_err,
        "equities":sum(1 for n in names if "FACTOR" not in (n.get("idx") or [])),
        "valCoveragePct":round(100.0*_cov.get("valOk",0)/max(sum(1 for n in names if "FACTOR" not in (n.get("idx") or [])),1),1),   # EQUITY-ONLY valuation coverage (ETFs have no P/E; counting them diluted it to ~62%)
        "fmpCoveragePct":round(100.0*_fmp_ok/max(_fmp_try,1),1),                  # FMP cross-check coverage specifically
        "gexCoveragePct":round(100.0*_eod_ok/max(_eod_try,1),1),
        # ---- PRICE-SOURCE HIERARCHY health: FMP Ultimate is PRIMARY; yfinance is the labeled BACKUP.
        #      The terminal reads these to show the source mix + the "FMP not pulling as of <ts>" alert. ----
        "priceSrc":{"fmp":PH["fmp"],"yfinance":PH["yf"],"miss":PH["miss"]},
        "fmpPricePrimary":True,
        "fmpLastOk":PH["fmpLastOk"],                                              # ISO ts of last successful FMP price pull
        "fmpDegraded":bool(PH["fmpKeyPresent"] and PH["fmp"]==0),                 # key present but 0 FMP prices -> alert
        "yfEnabled":PH["yfEnabled"],"yfImported":PH["yfImported"],
        "fmpPriceShare":round(100.0*PH["fmp"]/max(PH["fmp"]+PH["yf"]+PH["miss"],1),1),
        "coverage":_cov,"errs":_errs[:4]}
    return names,mkt,ff,macro

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--demo",action="store_true"); ap.add_argument("--real",action="store_true")
    ap.add_argument("--out",default="../../marketmap.json"); a=ap.parse_args()
    if a.real:
        names,mkt,ff,macro=real_universe()
        _PRECM={n["t"]: list(n["_cl"]) for n in names if n.get("_cl")}   # capture closes BEFORE build() pops _cl off each name (line ~542)
        snap=build(names,mkt,ff,macro); snap["source"]="Live · FMP Ultimate primary (prices/valuation) + macro factors + options OI; yfinance backup — research only"
        snap["dataHealth"]=globals().get("_DATA_HEALTH")
        # FMP Ultimate macro series (real Treasury curve + commodities) + per-driver provenance.
        _ms=globals().get("_MACRO_SERIES"); _msrc=globals().get("_MACRO_SRC")
        if _ms:
            snap["macroSeries"]=_ms
            snap["source"]="Live · FMP Ultimate primary (prices + rates/commodities/valuation + options OI); yfinance backup — research only"
        if _msrc: snap["macroSources"]=_msrc
        # SOURCE-LABEL honesty: reflect the actual price mix + raise the FMP-down banner inline so the
        # label itself communicates degradation even before the terminal renders the alert.
        try:
            _dhp=snap.get("dataHealth") or {}
            _ps=_dhp.get("priceSrc") or {}
            if _dhp.get("fmpDegraded"):
                _last=_dhp.get("fmpLastOk") or "never this run"
                snap["source"]="⚠ FMP Ultimate NOT pulling (last OK: %s) — serving yfinance backup · research only"%_last
            elif _ps.get("yfinance",0)>0 and _ps.get("fmp",0)>0:
                snap["source"]=snap["source"].replace("yfinance backup","yfinance backup [%d FMP / %d yfinance]"%(_ps.get("fmp",0),_ps.get("yfinance",0)))
        except Exception: pass
        # GRACEFUL DEGRADATION: if FMP returned nothing this run (dead/expired/limited key), keep the
        # last-good valuations from the live site instead of blanking the layer. Tagged stale=True.
        try:
            _dh=snap.get("dataHealth") or {}
            if _dh.get("fmpKey") and _dh.get("fmpOk",0)==0:
                import urllib.request as _ur, json as _cj, sys as _csys
                _prior={}
                with _ur.urlopen("https://mrktprice.com/marketmap.json", timeout=20) as _resp:
                    _pj=_cj.loads(_resp.read().decode("utf-8","ignore"))
                for _pn in (_pj.get("names") or []):
                    _pv=_pn.get("val")
                    if _pn.get("t") and isinstance(_pv,dict) and any(_pv.get(k) is not None for k in ("pe","fpe","peg","evb")):
                        _prior[_pn["t"]]=_pv
                _carried=0
                for _n in (snap.get("names") or []):
                    _pv=_prior.get(_n.get("t")); _cur=_n.get("val") or {}
                    if _pv and not any(_cur.get(k) is not None for k in ("pe","fpe","peg","evb")):
                        _pv=dict(_pv); _pv["stale"]=True; _n["val"]=_pv; _carried+=1
                snap["dataHealth"]["valCarriedForward"]=_carried
                _csys.stderr.write("FMP graceful: carried forward %d prior valuations (key not usable this run)\n"%_carried)
        except Exception as _ce:
            import sys as _csys2; _csys2.stderr.write("::notice::valuation carry-forward skipped: %s\n"%str(_ce)[:120])
        try:
            import xsection as _xsec, json as _json2, sys as _sys2
            _cm=_PRECM
            _mkt=_cm.get("SPY"); _rate=_cm.get("^TNX") or _cm.get("TLT") or _cm.get("IEF")
            _xj=_xsec.build_from_closes(_cm, market_closes=_mkt, rate_closes=_rate)
            _json2.dump(_xj, open(a.out.replace("marketmap.json","xsection.json"),"w"), separators=(",",":"), allow_nan=False)
            _sys2.stderr.write("XSECTION: %d tickers, %d days -> xsection.json\n"%(_xj.get("tickers",0),_xj.get("n",0)))
        except Exception as _xe:
            import sys as _sys3; _sys3.stderr.write("::warning::xsection build failed: %s\n"%str(_xe)[:120])
    else:
        names,mkt,ff,macro=synth(); snap=build(names,mkt,ff,macro)
    # ---- Phase 5.5: options-implied P/Q layer (needs gex.atmIV, set during enrichment) ----
    if _lineage is not None:
        try:
            _asof=dt.date.fromisoformat(str(snap.get("asof")))
        except Exception:
            _asof=None
        for _n in snap.get("names",[]):
            _lin=_n.get("lineage"); _gx=_n.get("gex") or {}
            if not isinstance(_lin,dict) or not _lin.get("horizons"): continue
            _ivp=_gx.get("atmIV")
            _iv=(_ivp/100.0) if isinstance(_ivp,(int,float)) and _ivp>0 else None
            _eda=None
            try:
                _nx=((_n.get("earn") or {}).get("next") or {}).get("d")
                if _nx and _asof: _eda=(dt.date.fromisoformat(str(_nx))-_asof).days
            except Exception:
                _eda=None
            try:
                _lin["pq"]=_lineage.pq_layer(_lin["horizons"], _iv, int(_gx.get("days") or 30), _eda)
            except Exception:
                pass
    # ---- Phase 5.5 + 6: options-implied P/Q layer + governance (ES, challenger gate, scan-risk,
    #      SIMM, provenance). Runs after enrichment so gex.atmIV / val / deps are populated. ----
    # ---- Phase 5.5 + 6: options-implied P/Q layer + governance (ES, challenger gate, scan-risk,
    #      SIMM, provenance). Runs after enrichment so gex.atmIV / val / deps are populated. ----
    # ---- Phase 5.5 + 6: options-implied P/Q layer + governance (ES, challenger gate, scan-risk,
    #      SIMM, provenance). Runs after enrichment so gex.atmIV / val / deps are populated. ----
    if _lineage is not None:
        _gov_counts={"deployable":0,"research-only":0,"blocked":0}
        _builtAt=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            _asof=dt.date.fromisoformat(str(snap.get("asof")))
        except Exception:
            _asof=None
        for _n in snap.get("names",[]):
            _lin=_n.get("lineage"); _gx=_n.get("gex") or {}
            if not isinstance(_lin,dict) or not _lin.get("horizons"): continue
            _ivp=_gx.get("atmIV")
            _iv=(_ivp/100.0) if isinstance(_ivp,(int,float)) and _ivp>0 else None
            _eda=None
            try:
                _nx=((_n.get("earn") or {}).get("next") or {}).get("d")
                if _nx and _asof: _eda=(dt.date.fromisoformat(str(_nx))-_asof).days
            except Exception:
                _eda=None
            try:
                _lin["pq"]=_lineage.pq_layer(_lin["horizons"], _iv, int(_gx.get("days") or 30), _eda)
            except Exception:
                pass
            try:
                _wr=_n.get("wr") or []
                _gov=_lineage.governance_block(_wr, _lin, _iv)
                _hh=_gov.get("horizon") or "20d"
                _pqh=((_lin.get("pq") or {}).get("horizons") or {}).get(_hh, {})
                _deps=(_n.get("macro3") or {}).get("top") or (_n.get("deps") or [])
                _gov["simm"]=_lineage.simm_decomp(_deps, _pqh.get("sigP"), _pqh.get("sigQ"))
                _exp=((_lin.get("factor") or {}).get("exposures") or {})
                _dws=[round(v,4) for v in _exp.values()][:8]
                if _dws: _gov["frtbSBA"]=_lineage.frtb_sba(_dws,[_gov["simm"].get("vega") or 0.0],_pqh.get("eventShare") or 0.0)
                _gov["stans"]=_lineage.stans_es(_wr)
                _srcs=["yfinance"]
                if _n.get("deps"): _srcs.append("FRED (macro)")
                if _gx: _srcs.append("EODHD (options)")
                if _n.get("val"): _srcs.append("FMP (valuation)")
                if _n.get("inst") or _n.get("insider"): _srcs.append("SEC EDGAR")
                _gov["provenance"]={"asof":snap.get("asof"),"modelVersion":"lineage-1.0","builtAt":_builtAt,
                    "sources":_srcs,"ivSource":("EODHD" if _gx else None),"histWeeks":len(_wr)}
                _lin["gov"]=_gov
                _g=_gov.get("releaseGate","blocked"); _g="blocked" if str(_g).startswith("blocked") else _g
                if _g in _gov_counts: _gov_counts[_g]+=1
                _sigby={}
                for _lab,_h in (_lin.get("horizons") or {}).items():
                    _ph=((_lin.get("pq") or {}).get("horizons") or {}).get(_lab) or {}
                    _sigby[_lab]=_ph.get("sigHouse") or _h.get("totVol")
                _cube=_lineage.scenario_cube(_sigby)
                if _cube: _lin["cube"]=_cube
                _bl=_lin.get("bl") or {}; _post=_lin.get("post") or []; _means=_lin.get("means") or []
                _blh=((_bl.get("horizons") or {}).get(_hh) or {})
                if _post and _means and len(_post)==len(_means) and _blh.get("postMu") is not None:
                    _stp={"intraday":0.25,"1d":1,"5d":5,"10d":10,"20d":20,"63d":63}.get(_hh,20)/5.0
                    _q=_lineage.entropy_pool_regimes(_post,[m*_stp for m in _means],_blh["postMu"])
                    if _q:
                        _bl["entropyApplied"]=True; _bl["entropyPost"]=_q
            except Exception:
                pass
        snap["governance"]={"counts":_gov_counts,"modelVersion":"lineage-1.0","builtAt":_builtAt,"asof":snap.get("asof")}
    def _finite(o):
        if isinstance(o,float): return o if (o==o and o not in (float("inf"),float("-inf"))) else 0.0
        if isinstance(o,list): return [_finite(x) for x in o]
        if isinstance(o,dict): return {k:_finite(v) for k,v in o.items()}
        return o
    # ---- FACTOR EVALUATION STACK (forward-IC weighted, BH-FDR gated, sign-aware) + REAL-RATE CURVE ----
    try:
        import os as _o2, sys as _s2, factor_pipeline as _fpipe, rate_real as _rr
        _store=_o2.path.dirname(_o2.path.abspath(__file__))
        _etf=set((nn.get("t") or "").upper() for nn in names if ("ETF" in (nn.get("idx") or []) or nn.get("etf")))
        _fx=_fpipe.run(names, _store, is_etf=lambda t:(t in _etf))
        for _k in ("factorWeights","factorMode","factorBreadth","factorIC","factorHistoryN","compositeGate","convictionScale"):
            if _k in _fx: snap[_k]=_fx[_k]
        _calc=_fx.get("calc") or {}
        for _nn in names:
            _cc=_calc.get((_nn.get("t") or "").upper())
            if _cc: _nn["calc"]=_cc                                          # per-name velocity/accel/accumulation
        try:
            _ch=_rr.fetch_real_curve_history()
            if _ch:
                _cs=_rr.curve_state(_ch)
                if _cs: snap["realCurve"]=_cs                                # Diebold-Li real L/S/C + dL/dS/dC
                try: snap["rateBetaN"]=_rr.attach_duration_betas(names, _ch, is_etf=lambda t:(t in _etf))   # per-name n['rate']={bL,tL,...,class}
                except Exception: pass
        except Exception: pass
        _s2.stderr.write("FACTOR STACK: mode=%s breadth=%s histN=%s curve=%s\n"%(_fx.get("factorMode"),_fx.get("factorBreadth"),_fx.get("factorHistoryN"),bool(snap.get("realCurve"))))
    except Exception as _fe2:
        try:
            import sys as _s3; _s3.stderr.write("::warning::factor stack skipped: %s\n"%str(_fe2)[:160])
        except Exception: pass
    # ---- TRIGGER-OUTCOME CALIBRATION: snapshot per-name gate metrics, mature with realized fwd returns,
    #      walk-forward fit the intraday cutoffs (degrade to literature defaults until history accrues) ----
    try:
        import os as _o3, trigger_store as _tstore, threshold_calib as _tcal, datetime as _dt3
        _st2=_o3.path.dirname(_o3.path.abspath(__file__))
        _etf2=set((nn.get("t") or "").upper() for nn in names if ("ETF" in (nn.get("idx") or []) or nn.get("etf")))
        _tsnap=_o3.path.join(_st2,"trig_snap.jsonl"); _tout=_o3.path.join(_st2,"trig_out.jsonl"); _td=_dt3.date.today().isoformat()
        _trows=[]; _pxn={}
        for nn in names:
            _tt=(nn.get("t") or "").upper()
            if not _tt or _tt in _etf2: continue
            _mm=_tstore.metrics_for(nn.get("_cl") or [], nn.get("_vol") or [])
            if _mm: _trows.append({"t":_tt,"m":_mm}); _pxn[_tt]=_mm["px"]
        if _trows:
            _tstore.snapshot(_tsnap,_td,_trows); _tstore.mature(_tsnap,_tout,_td,20,_pxn)
            _mets={}
            for _k3,_g3 in (("rvol",[1.5,2.0,2.5,3.0]),("z",[1.5,2.0,2.5]),("obvt",[1.5,2.0,2.5])):
                _oc=_tstore.read_outcomes(_tout,_k3); _mets[_k3]={"values":_oc["values"],"fwd":_oc["fwd"],"grid":_g3,"side":"ge","min_hits":20}
            snap["triggerCutoffs"]=_tcal.calibrate(_mets, defaults={"rvol":2.0,"z":2.0,"obvt":2.0})
    except Exception: pass
    # ---- PER-NAME DRIFT (run-over-run, checkpointed): PSI/KS of each name's return distribution vs a
    #      RETAINED reference window (drift_ref.json, refreshed ~monthly) + an immediate in-sample drift.
    #      Flags regime change / a provider changing basis / corrupted pulls. Uses _PRECM (closes captured
    #      before build() popped _cl). Persisted via drift_store.jsonl + drift_ref.json (committed nightly). ----
    try:
        import os as _o4, drift_store as _drift
        _st4 = _o4.path.dirname(_o4.path.abspath(__file__))
        _rmap = {}
        for _n in (snap.get("names") or []):
            _t = (_n.get("t") or "").upper(); _cl = _PRECM.get(_t)
            if not _t or not _cl or len(_cl) < 41:
                continue
            _rmap[_t] = [_cl[i] / _cl[i - 1] - 1.0 for i in range(1, len(_cl)) if _cl[i - 1]]
        if _rmap:
            _dout = _drift.update(_o4.path.join(_st4, "drift_ref.json"), _o4.path.join(_st4, "drift_store.jsonl"),
                                  snap.get("asof"), _rmap)
            for _n in (snap.get("names") or []):
                _dd = _dout.get((_n.get("t") or "").upper())
                if _dd:
                    _n["drift"] = _dd
            if isinstance(snap.get("dataHealth"), dict):
                snap["dataHealth"]["driftCensus"] = _drift.census(_dout)
    except Exception as _de:
        import sys as _s4; _s4.stderr.write("::warning::drift layer skipped: %s\n" % str(_de)[:140])
    # ---- OUTPUT INTEGRITY: a PUBLIC per-node data-quality verdict (n['dq']) the board can act on, a
    #      bounded-output sanitizer (broken/degenerate equation outputs -> null + count), and a run-over-run
    #      health/credibility trend (health_log.jsonl). Honest degradation at the output boundary. ----
    try:
        import os as _o5, json as _j5, data_quality as _dqm
        _st5=_o5.path.dirname(_o5.path.abspath(__file__))
        _sani=0
        _BOUNDS={"beta":(-15.0,15.0),"maxDD":(-1.0,0.0),"dvol":(0.0,6.0),"hv":(0.0,6.0),"rvol":(0.0,500.0),"atr":(0.0,1e7)}
        for _n in (snap.get("names") or []):
            _t=(_n.get("t") or "").upper(); _cl=_PRECM.get(_t)
            if _cl and len(_cl)>=20:
                try: _n["dq"]=_dqm.series_health(_cl, None)["verdict"]
                except Exception: pass
            for _k,(_lo,_hi) in _BOUNDS.items():
                if _n.get(_k) is not None:
                    _gv,_gr=_dqm.guard(_n.get(_k),_lo,_hi,_k)
                    if _gv is None: _n[_k]=None; _sani+=1
        if isinstance(snap.get("dataHealth"),dict): snap["dataHealth"]["sanitizedFields"]=_sani
        # PROVENANCE: a REAL raw-data hash (sha256 of the canonical input close panel) + a config hash
        # (sha256 of the composite weights/params), so a pooled run is reproducible — same data + config
        # reproduce the same outputs — beyond qa_signoff's source-code fingerprint.
        try:
            import hashlib as _hl
            _raw={_t:[round(_x,4) for _x in (_PRECM.get(_t) or [])] for _t in sorted(_PRECM)}
            _rawh=_hl.sha256(_j5.dumps(_raw,separators=(",",":"),sort_keys=True).encode("utf-8")).hexdigest()
            _cfg={"weights":{"sMR":0.35,"sMom":0.30,"sSig":0.25,"sVol":0.10},"thr":0.3,"H":10,"schema":snap.get("schemaVersion")}
            _cfgh=_hl.sha256(_j5.dumps(_cfg,separators=(",",":"),sort_keys=True).encode("utf-8")).hexdigest()
            if isinstance(snap.get("dataHealth"),dict):
                snap["dataHealth"]["rawDataHash"]=_rawh; snap["dataHealth"]["configHash"]=_cfgh
        except Exception: pass
        try:
            _dh5=snap.get("dataHealth") or {}; _dq5=_dh5.get("dataQuality") or {}; _drc5=_dh5.get("driftCensus") or {}
            _hl={"asof":snap.get("asof"),"source":(snap.get("source") or "")[:70],
                 "dataQuality":{_kk:_dq5.get(_kk) for _kk in ("clean","degraded","reject")} if _dq5 else None,
                 "priceSrc":_dh5.get("priceSrc"),"fmpLastOk":_dh5.get("fmpLastOk"),"fmpDegraded":_dh5.get("fmpDegraded"),
                 "rateSource":(snap.get("realCurve") or {}).get("source"),
                 "driftCensus":{_kk:_drc5.get(_kk) for _kk in ("stable","moderate","significant","baseline")} if _drc5 else None,
                 "sanitizedFields":_sani}
            with open(_o5.path.join(_st5,"health_log.jsonl"),"a",encoding="utf-8") as _f5: _f5.write(_j5.dumps(_hl)+"\n")
        except Exception: pass
    except Exception as _se:
        import sys as _s5; _s5.stderr.write("::warning::output-integrity layer skipped: %s\n"%str(_se)[:140])
    # ---- EVENT-AWARE LAYER: high-impact US macro calendar (FMP) -> snap['events'] (next event + window +
    #      daysToNext) so the conviction/drift layers can treat signals cautiously right before a major
    #      print and expect a distribution shift right after one. Fail-soft (no key / no data -> skipped). ----
    try:
        import events_calendar as _ev
        _evraw=_ev.fetch_economic_calendar()
        if _evraw is not None: snap["events"]=_ev.build_events(_evraw)
    except Exception: pass
    snap.setdefault("schemaVersion","1.0")                                 # producer-stamped contract version (consumer version-gates)
    snap=_finite(snap)
    json.dump(snap,open(a.out,"w"),separators=(",",":"),allow_nan=False)   # allow_nan=False = hard guard: never emit invalid JSON
    print(f"wrote {a.out}: {len(names)} names, asof {snap['asof']}, source={snap['source'][:24]}")

if __name__=="__main__":
    main()
