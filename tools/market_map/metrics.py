#!/usr/bin/env python3
"""
metrics.py — pure metric math for the Market Map build, extracted verbatim from build_market_map.py.

These are side-effect-free, stdlib-only estimators (winsorize/z-scores, beta/pearson/partial corr,
exact Student-t p, OLS, PCA cluster order, money flow, MFI/ATR, Lasso CD, EMA, OU half-life, variance
ratio, Parkinson vol, jump ratio, first-passage touch probabilities, contradiction, and the touch
reliability backtest). Pulling them out keeps build_market_map.py UNDER the sandbox mount's read
boundary (~1756 lines) so the whole monolith parses through the mount — and makes this library
independently unit-tested in test_metrics.py. See tools/MOUNT_VERIFICATION_PROTOCOL.md.
"""
import math

__all__ = ["winsorize", "zscores", "ann_vol", "beta", "pearson", "_var", "_resid_on", "partial_corr",
           "_betacf", "_betai", "_t_two_sided_p", "ols_betas", "cluster_order", "money_flow", "MACROF",
           "_ok", "mfi", "atr", "zstd", "lasso_cd", "macro_fit", "ema_series", "daily_logvol", "_logret",
           "half_life", "variance_ratio", "parkinson_vol", "jump_ratio", "_phi", "prob_touch",
           "contradiction", "_Q75", "median_touch_days", "_dvol", "regime_flip_prob", "calibrate_touch",
           # canonical risk/return library (previously missing or duplicated across modules):
           "mean", "stdev", "sharpe", "downside_dev", "sortino", "max_drawdown", "calmar", "cagr",
           "skewness", "kurtosis", "value_at_risk", "cvar", "ulcer_index", "information_ratio",
           "ewma_vol", "spearman", "hurst"]


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


# ============================================================================================
# CANONICAL RISK / RETURN LIBRARY
# Audit finding: sharpe was duplicated (composite_gate.py + pooled_rigor.py), spearman duplicated
# (factor_eval.py + signal_linkage.py), ewma in 3 modules; and Sortino/Calmar/skew/kurtosis/CVaR/
# Hurst/information-ratio/max-drawdown existed NOWHERE in Python. These are the single source of truth.
# All pure-stdlib, NaN/None-robust, unit-tested in test_metrics.py.
# ============================================================================================
def _clean(xs):
    return [float(x) for x in xs if x is not None and x == x]

def mean(xs):
    v = _clean(xs); return sum(v) / len(v) if v else float("nan")

def stdev(xs, ddof=1):
    v = _clean(xs)
    if len(v) <= ddof: return float("nan")
    m = sum(v) / len(v); return (sum((x - m) ** 2 for x in v) / (len(v) - ddof)) ** 0.5

def sharpe(returns, rf=0.0, periods=252):
    """Annualized Sharpe of a per-period simple-return series (rf annualized)."""
    v = _clean(returns)
    if len(v) < 2: return float("nan")
    ex = [x - rf / periods for x in v]; sd = stdev(ex)
    if not sd or sd != sd: return float("nan")
    return (sum(ex) / len(ex)) / sd * math.sqrt(periods)

def downside_dev(returns, mar=0.0, periods=252):
    """Annualized downside deviation below a minimum-acceptable return (full-sample denominator)."""
    v = _clean(returns)
    if not v: return float("nan")
    d = [min(0.0, x - mar / periods) for x in v]
    return (sum(x * x for x in d) / len(v)) ** 0.5 * math.sqrt(periods)

def sortino(returns, rf=0.0, periods=252):
    v = _clean(returns)
    if len(v) < 2: return float("nan")
    dd = downside_dev(v, rf, periods)
    if not dd or dd != dd: return float("nan")
    return (sum(x - rf / periods for x in v) / len(v)) * periods / dd

def max_drawdown(equity_or_prices):
    """Max peak-to-trough drawdown (fraction in [-1,0]) of a price/equity LEVEL series."""
    v = _clean(equity_or_prices)
    if len(v) < 2: return 0.0
    peak = v[0]; mdd = 0.0
    for x in v:
        if x > peak: peak = x
        if peak > 0: mdd = min(mdd, x / peak - 1.0)
    return round(mdd, 6)

def cagr(returns, periods=252):
    v = _clean(returns)
    if not v: return float("nan")
    eq = 1.0
    for r in v: eq *= (1.0 + r)
    return eq ** (periods / len(v)) - 1.0

def calmar(returns, periods=252):
    """Annualized return / |max drawdown| of the cumulative equity built from the returns."""
    v = _clean(returns)
    if len(v) < 2: return float("nan")
    eq = [1.0]
    for r in v: eq.append(eq[-1] * (1.0 + r))
    mdd = max_drawdown(eq)
    return (cagr(v, periods) / abs(mdd)) if mdd < 0 else float("nan")

def skewness(xs):
    """Sample (bias-corrected) skewness."""
    v = _clean(xs); n = len(v)
    if n < 3: return float("nan")
    m = sum(v) / n; sd = (sum((x - m) ** 2 for x in v) / n) ** 0.5
    if sd == 0: return 0.0
    return (n / ((n - 1) * (n - 2))) * sum(((x - m) / sd) ** 3 for x in v)

def kurtosis(xs, excess=True):
    """Sample (bias-corrected) excess kurtosis (set excess=False for raw)."""
    v = _clean(xs); n = len(v)
    if n < 4: return float("nan")
    m = sum(v) / n; sd = (sum((x - m) ** 2 for x in v) / n) ** 0.5
    if sd == 0: return 0.0
    g2 = (n * (n + 1) / ((n - 1) * (n - 2) * (n - 3))) * sum(((x - m) / sd) ** 4 for x in v) \
        - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    return g2 if excess else g2 + 3.0

def value_at_risk(returns, alpha=0.05):
    """Historical VaR at level alpha (positive number = loss magnitude)."""
    v = sorted(_clean(returns))
    if not v: return float("nan")
    i = max(0, min(len(v) - 1, int(alpha * len(v))))
    return -v[i]

def cvar(returns, alpha=0.05):
    """Historical CVaR / expected shortfall: mean of the worst alpha tail (positive = avg loss)."""
    v = sorted(_clean(returns))
    if not v: return float("nan")
    k = max(1, int(alpha * len(v))); tail = v[:k]
    return -(sum(tail) / len(tail))

def ulcer_index(prices):
    """Ulcer Index: RMS of percent drawdowns from the running peak (downside-only risk)."""
    v = _clean(prices)
    if len(v) < 2: return float("nan")
    peak = v[0]; s = 0.0
    for x in v:
        if x > peak: peak = x
        dd = 100.0 * (x / peak - 1.0) if peak > 0 else 0.0
        s += dd * dd
    return (s / len(v)) ** 0.5

def information_ratio(returns, bench, periods=252):
    """Annualized active-return / tracking-error vs a benchmark return series."""
    a = _clean(returns); b = _clean(bench); n = min(len(a), len(b))
    if n < 2: return float("nan")
    act = [a[i] - b[i] for i in range(n)]; te = stdev(act)
    if not te or te != te: return float("nan")
    return (sum(act) / n) / te * math.sqrt(periods)

def ewma_vol(returns, lam=0.94, annualize=252):
    """RiskMetrics EWMA volatility; annualized if `annualize` periods/yr else per-period."""
    v = _clean(returns)
    if not v: return float("nan")
    var = v[0] * v[0]
    for r in v[1:]: var = lam * var + (1 - lam) * r * r
    s = var ** 0.5
    return s * math.sqrt(annualize) if annualize else s

def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i]); rk = [0.0] * len(xs); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]: j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1): rk[order[k]] = avg
        i = j + 1
    return rk

def spearman(a, b):
    """Spearman rank correlation (ties averaged). Canonical home for the duplicated copies."""
    pr = [(x, y) for x, y in zip(a, b) if x == x and y == y]
    if len(pr) < 3: return float("nan")
    return pearson(_rank([p[0] for p in pr]), _rank([p[1] for p in pr]))

def hurst(prices, max_lag=20):
    """Hurst exponent via lag-variance (log-price) regression. H>0.5 trending, <0.5 mean-reverting."""
    v = [math.log(x) for x in _clean(prices) if x > 0]
    n = len(v)
    if n < 2 * max_lag + 8: return None
    lags = list(range(2, max_lag + 1)); tau = []
    for L in lags:
        d = [v[i] - v[i - L] for i in range(L, n)]
        if len(d) < 3: return None
        m = sum(d) / len(d); s = (sum((x - m) ** 2 for x in d) / len(d)) ** 0.5
        tau.append(s if s > 0 else 1e-12)
    b = beta([math.log(t) for t in tau], [math.log(L) for L in lags])   # slope = H
    return round(b, 3) if b == b else None
