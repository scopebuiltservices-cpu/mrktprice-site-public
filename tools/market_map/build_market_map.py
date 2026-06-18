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
import argparse, json, math, os, random, sys, datetime as dt

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

def membership(code):
    p=code.split(); idx=[]
    if "ND" in p: idx.append("NDX")
    if "D" in p: idx.append("DOW")
    if "S" in p: idx.append("SPX")
    if "R" in p: idx.append("RUT")
    return sorted(set(idx)) or ["SPX"]

SECMACRO={"Energy":{"OIL":1.10,"DXY":-0.20},"Financials":{"RATE":0.55,"DXY":0.10},
 "Materials":{"OIL":0.45,"DXY":-0.30},"Utilities":{"RATE":-0.55},"Real Estate":{"RATE":-0.60},
 "Technology":{"RATE":-0.30,"VIX":-0.25},"Consumer Disc.":{"RATE":-0.20,"VIX":-0.25},
 "Communication":{"VIX":-0.20},"Industrials":{"OIL":0.25},"Consumer Staples":{"VIX":0.10},"Health Care":{}}

def synth(seed=7):
    rng=random.Random(seed); W=53
    mkt=[rng.gauss(0.002,0.022) for _ in range(W)]
    secf={s:[rng.gauss(0,0.012) for _ in range(W)] for s in SECTORS}
    ff={"SMB":[rng.gauss(0,0.01) for _ in range(W)],"HML":[rng.gauss(0,0.01) for _ in range(W)],"MOM":[rng.gauss(0,0.01) for _ in range(W)]}
    macro={"DXY":[rng.gauss(0,0.008) for _ in range(W)],"RATE":[rng.gauss(0,0.012) for _ in range(W)],
           "VIX":[rng.gauss(0,0.05) for _ in range(W)],"OIL":[rng.gauss(0,0.03) for _ in range(W)]}
    names=[]
    def mk(sym,nm,sec,idx,mcaprange,idiorange,liquid):
        b=rng.uniform(*[0.6,1.6] if liquid else [0.7,1.9]); sl=rng.uniform(0.5,1.2)
        cs,ch,cm=rng.uniform(-0.8,0.8),rng.uniform(-0.8,0.8),rng.uniform(-0.6,0.6); idio=rng.uniform(*idiorange)
        mb={f:SECMACRO.get(sec,{}).get(f,0.0)+rng.gauss(0,0.12) for f in ("DXY","RATE","VIX","OIL")}
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
        rec={"t":sym,"n":nm,"sec":sec,"idx":idx,"mcap":round(mcap),
             "wr":[round(x,5) for x in wr],"_cl":closes,"_hi":highs,"_lo":lows,"_vol":vols,"_fcf":fcf}
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
    MFAC=[f for f in ("DXY","RATE","VIX","OIL") if f in macro and len(macro[f])==len(mkt)]
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
    risk=[n["beta"] for n in names]; size=[math.log(n["mcap"]) for n in names]
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
        if n.get("contra") and n["contra"]["s"]<=0.2 and n.get("ema21d",0)>0: al.append("aligned uptrend")
        n["alerts"]=al[:4]
    secmean={}
    for s in SECTORS:
        mem=[n["wr"] for n in names if n["sec"]==s]
        if mem: secmean[s]=[sum(m[w] for m in mem)/len(mem) for w in range(len(mem[0]))]
    osec=[s for s in SECTORS if s in secmean]
    M=[[round(pearson(secmean[a],secmean[b]),3) for b in osec] for a in osec]
    oi=cluster_order(M); osec=[osec[i] for i in oi]; M=[[M[i][j] for j in oi] for i in oi]
    # ---- directional dependency list: which macro deltas / sector the name moves WITH or AGAINST ----
    FACS=[("MKT",mkt,"S&P 500"),("RATE",macro.get("RATE"),"10Y yield"),("DXY",macro.get("DXY"),"US dollar"),
          ("OIL",macro.get("OIL"),"WTI oil"),("VIX",macro.get("VIX"),"VIX")]
    for n in names:
        wr=n["wr"]; deps=[]
        for fk,ser,lab in FACS:
            if not ser: continue
            c=pearson(wr,ser)
            if c==c and abs(c)>=0.12:
                deps.append({"f":lab,"corr":round(c,2),"dir":("with" if c>0 else "against")})
        sc=secmean.get(n["sec"])
        if sc:
            c=pearson(wr,sc)
            if c==c and abs(c)>=0.12: deps.append({"f":n["sec"]+" sector","corr":round(c,2),"dir":("with" if c>0 else "against")})
        deps.sort(key=lambda d:-abs(d["corr"])); n["deps"]=deps[:6]
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
            "names":names,"sectorCorr":{"order":osec,"m":M}}

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

def finnhub_beat(key, names, cap=60):
    """Finnhub consensus earnings -> historical beat-rate -> P(beat next) (Bayesian-shrunk).
    Sets n['_beat']; build() folds it into the odds ladder. Capped to the most-liquid big-3 names."""
    import requests
    big=[n for n in names if "RUT" not in n.get("idx",[])][:cap]
    for n in big:
        try:
            r=requests.get("https://finnhub.io/api/v1/stock/earnings",
                           params={"symbol":n["t"],"token":key},timeout=15)
            arr=r.json()
            if not isinstance(arr,list): continue
            tot=[e for e in arr if e.get("surprisePercent") is not None]
            if not tot: continue
            beats=[e for e in tot if e["surprisePercent"]>=0]
            n["_beat"]=round((len(beats)+1.0)/(len(tot)+2.0),2)   # shrink toward 0.5
        except Exception: continue

def twelvedata_ivol(key, names, cap=40):
    """Twelve Data 1h bars -> annualized INTRADAY realized vol (P3-18 family). Sets n['ivol']."""
    import requests
    big=sorted([n for n in names if "RUT" not in n.get("idx",[])], key=lambda n:-n.get("mcap",0))[:cap]
    for n in big:
        try:
            r=requests.get("https://api.twelvedata.com/time_series",
                params={"symbol":n["t"],"interval":"1h","outputsize":"200","apikey":key},timeout=15)
            v=r.json().get("values",[])
            cl=[float(x["close"]) for x in v if x.get("close")][::-1]
            if len(cl)<30: continue
            rr=[math.log(cl[i]/cl[i-1]) for i in range(1,len(cl)) if cl[i-1]>0 and cl[i]>0]
            if len(rr)<10: continue
            mu=sum(rr)/len(rr); sd=(sum((x-mu)**2 for x in rr)/(len(rr)-1))**0.5
            n["ivol"]=round(sd*math.sqrt(252*6.5)*100,1)
        except Exception: continue

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
    import yfinance as yf
    for sym,nm,sec_name,code in SEED:        # phase-1 universe (extend to full big-3 once holdings parse is wired)
        try:
            h=yf.Ticker(sym).history(period="1y",interval="1d",auto_adjust=True)
            cl=[];vo=[];hi=[];lo=[]
            for c,v,H,Lw in zip(h["Close"].tolist(), h["Volume"].tolist(), h["High"].tolist(), h["Low"].tolist()):
                c=float(c); v=float(v)
                if c==c and c>0:                     # drop NaN / non-positive closes, keep alignment
                    cl.append(c); vo.append(v if v==v else 0.0)
                    H=float(H); Lw=float(Lw); hi.append(H if H==H else c); lo.append(Lw if Lw==Lw else c)
            if len(cl)<10: raise ValueError("insufficient history")
            wk=cl[::5]; wr=[(wk[i]/wk[i-1]-1) for i in range(1,len(wk)) if wk[i-1]]
            info=yf.Ticker(sym).get_info(); mcap=float(info.get("marketCap") or 0) or (cl[-1]*float(info.get("sharesOutstanding") or 0))
            fcf=info.get("freeCashflow")
            names.append({"t":sym,"n":nm,"sec":sec_name,"idx":membership(code),"mcap":round(mcap or 1e9),
                          "wr":[round(x,5) for x in wr],"_cl":cl,"_hi":hi,"_lo":lo,"_vol":vo,"_fcf":float(fcf) if fcf else None})
        except Exception as e:
            sys.stderr.write(f"skip {sym}: {e}\n")
    # ---- Russell 2000 (phase 2): iShares IWM holdings, batch-downloaded (env RUSSELL_LIMIT caps size; 0 = all) ----
    try:
        lim=int(os.environ.get("RUSSELL_LIMIT","2000")); lim=lim or None
        rus=fetch_russell(yf, lim, UA)
        sys.stderr.write(f"russell: fetched {len(rus)} constituents\n"); names+=rus
    except Exception as e:
        sys.stderr.write(f"russell skip: {e}\n")
    # market proxy = SPY weekly
    def _wret(sym):
        try:
            h=yf.Ticker(sym).history(period="1y",interval="1d",auto_adjust=True)
            c=[float(x) for x in h["Close"].tolist() if float(x)==float(x) and float(x)>0]
            w=c[::5]; return [(w[i]/w[i-1]-1) for i in range(1,len(w)) if w[i-1]]
        except Exception: return []
    mkt=_wret("SPY") or [0.0]*52
    ff={"SMB":[0.0]*len(mkt),"HML":[0.0]*len(mkt),"MOM":[0.0]*len(mkt)}  # FF factors optional; default 0 if no source
    # ---- macro factor panel (free proxies) for the sparse Lasso attribution + dislocation ----
    macro={"DXY":_wret("DX-Y.NYB") or _wret("UUP"),"RATE":_wret("^TNX"),
           "VIX":_wret("^VIX"),"OIL":_wret("CL=F") or _wret("USO")}
    macro={k:(v if len(v)==len(mkt) else (v[-len(mkt):] if len(v)>len(mkt) else v+[0.0]*(len(mkt)-len(v)))) for k,v in macro.items()}
    # ---- optional FREE connectors (gated by repo-secret keys; degrade gracefully when unset) ----
    fk=os.environ.get("FRED_API_KEY","").strip()
    if fk:
        try:
            fm=fred_macro(fk)
            for k,v in fm.items():
                macro[k]=(v if len(v)==len(mkt) else (v[-len(mkt):] if len(v)>len(mkt) else v+[0.0]*(len(mkt)-len(v))))
            sys.stderr.write(f"FRED macro: {len(fm)} official series\n")
        except Exception as e: sys.stderr.write(f"FRED skip: {e}\n")
    ek=os.environ.get("FINNHUB_API_KEY","").strip()
    if ek:
        try: finnhub_beat(ek, names); sys.stderr.write("Finnhub estimates: beat-prob set\n")
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
    return names,mkt,ff,macro

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--demo",action="store_true"); ap.add_argument("--real",action="store_true")
    ap.add_argument("--out",default="../../marketmap.json"); a=ap.parse_args()
    if a.real:
        names,mkt,ff,macro=real_universe(); snap=build(names,mkt,ff,macro); snap["source"]="Live (yfinance + macro factors + options OI) — research only"
    else:
        names,mkt,ff,macro=synth(); snap=build(names,mkt,ff,macro)
    def _finite(o):
        if isinstance(o,float): return o if (o==o and o not in (float("inf"),float("-inf"))) else 0.0
        if isinstance(o,list): return [_finite(x) for x in o]
        if isinstance(o,dict): return {k:_finite(v) for k,v in o.items()}
        return o
    snap=_finite(snap)
    json.dump(snap,open(a.out,"w"),separators=(",",":"),allow_nan=False)   # allow_nan=False = hard guard: never emit invalid JSON
    print(f"wrote {a.out}: {len(names)} names, asof {snap['asof']}, source={snap['source'][:24]}")

if __name__=="__main__":
    main()
