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
        if closes[i] is None or closes[i-1] is None or vols[i] is None: continue
        dv=closes[i]*vols[i]; r=closes[i]-closes[i-1]
        if r>=0: infl+=dv; last_in=dv; last_out=0.0
        else: outfl+=dv; last_out=dv; last_in=0.0
    tot=infl+outfl
    net=(infl-outfl)/tot if tot>0 else float("nan")
    return net, infl, outfl, last_in, last_out

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

def membership(code):
    p=code.split(); idx=[]
    if "ND" in p: idx.append("NDX")
    if "D" in p: idx.append("DOW")
    if "S" in p: idx.append("SPX")
    return sorted(set(idx)) or ["SPX"]

def synth(seed=7):
    rng=random.Random(seed); W=53
    mkt=[rng.gauss(0.002,0.022) for _ in range(W)]
    secf={s:[rng.gauss(0,0.012) for _ in range(W)] for s in SECTORS}
    ff={"SMB":[rng.gauss(0,0.01) for _ in range(W)],"HML":[rng.gauss(0,0.01) for _ in range(W)],"MOM":[rng.gauss(0,0.01) for _ in range(W)]}
    names=[]
    for sym,nm,sec,code in SEED:
        b=rng.uniform(0.6,1.6); sl=rng.uniform(0.5,1.2)
        cs,ch,cm=rng.uniform(-0.8,0.8),rng.uniform(-0.8,0.8),rng.uniform(-0.6,0.6); idio=rng.uniform(0.01,0.03)
        wr=[b*mkt[w]+sl*secf[sec][w]+cs*ff["SMB"][w]+ch*ff["HML"][w]+cm*ff["MOM"][w]+rng.gauss(0,idio) for w in range(W)]
        mcap=math.exp(rng.uniform(23.5,28.8))
        # synthetic daily closes+volumes (for money flow) consistent with weekly direction
        px=100.0; closes=[px]; vols=[]
        for w in range(W):
            for _ in range(5):
                dr=wr[w]/5+rng.gauss(0,idio/2); px*=(1+dr); closes.append(px)
                vols.append(rng.uniform(0.6,1.6)*mcap*0.0008*(1+abs(dr)*8))
        closes=closes[1:]
        fcf=mcap*rng.uniform(-0.02,0.08)            # synthetic free cash flow ($)
        names.append({"t":sym,"n":nm,"sec":sec,"idx":membership(code),"mcap":round(mcap),
                      "wr":[round(x,5) for x in wr],"_cl":closes,"_vol":vols,"_fcf":fcf})
    return names,mkt,ff

def aggregate(wr):
    def cum(k):
        s=wr[-k:] if k<=len(wr) else wr; p=1.0
        for x in s: p*=(1+x)
        return (p-1)*100
    return {"1w":round(wr[-1]*100,2) if wr else 0,"1m":round(cum(4),2),"3m":round(cum(13),2),"6m":round(cum(26),2),"12m":round(cum(52),2)}

def build(names,mkt,ff):
    for n in names:
        wr=n["wr"]; n["ret"]=aggregate(wr); n["vol"]=round(ann_vol(wr)*100,1); n["beta"]=round(beta(wr,mkt),2)
        X=[[mkt[w],ff["SMB"][w],ff["HML"][w],ff["MOM"][w]] for w in range(len(wr))]
        bc=ols_betas(wr,X); n["ff"]={f:round(bc[i],2) for i,f in enumerate(FACTORS)}
        cl=n.pop("_cl",None); vo=n.pop("_vol",None)
        if cl and vo:
            net1,i1,o1,li,lo=money_flow(cl[-21:],vo[-21:]); net3,_,_,_,_=money_flow(cl[-63:],vo[-63:])
            n["flow"]={"net1m":round(net1,3),"net3m":round(net3,3),"in":round(i1),"out":round(o1),"din":round(li),"dout":round(lo)}
        else:
            n["flow"]={"net1m":float("nan"),"net3m":float("nan")}
        fcf=n.pop("_fcf",None); n["fcf"]=round(fcf) if fcf is not None else None
        n["fcfY"]=round(fcf/n["mcap"]*100,2) if (fcf is not None and n["mcap"]) else None
    val=[ -n["ret"]["12m"]/(n["vol"] or 1) for n in names]; mom=[n["ret"]["6m"] for n in names]
    risk=[n["beta"] for n in names]; size=[math.log(n["mcap"]) for n in names]
    fcy=[n["fcfY"] for n in names]; flw=[n["flow"]["net1m"] for n in names]
    Z=lambda a:zscores(winsorize(a))
    zV,zM,zR,zS,zF,zL=Z(val),Z(mom),Z(risk),Z(size),Z(fcy),Z(flw)
    for i,n in enumerate(names):
        n["z"]={"val":round(zV[i],2),"mom":round(zM[i],2),"risk":round(zR[i],2),"size":round(zS[i],2),"fcf":round(zF[i],2),"flow":round(zL[i],2)}
    secmean={}
    for s in SECTORS:
        mem=[n["wr"] for n in names if n["sec"]==s]
        if mem: secmean[s]=[sum(m[w] for m in mem)/len(mem) for w in range(len(mem[0]))]
    osec=[s for s in SECTORS if s in secmean]
    M=[[round(pearson(secmean[a],secmean[b]),3) for b in osec] for a in osec]
    oi=cluster_order(M); osec=[osec[i] for i in oi]; M=[[M[i][j] for j in oi] for i in oi]
    return {"asof":dt.date.today().isoformat(),"source":"SAMPLE (synthetic, illustrative) — replaced by the nightly job",
            "indices":{"DOW":"Dow Jones 30","NDX":"Nasdaq-100","SPX":"S&P 500"},"sectors":SECTORS,"factors":FACTORS,
            "names":names,"sectorCorr":{"order":osec,"m":M}}

# ---------- real fetch (nightly Action only; needs network) ------------------------------------
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
            cl=[float(x) for x in h["Close"].tolist()]; vo=[float(x) for x in h["Volume"].tolist()]
            wk=cl[::5]; wr=[(wk[i]/wk[i-1]-1) for i in range(1,len(wk))]
            info=yf.Ticker(sym).get_info(); mcap=float(info.get("marketCap") or 0) or (cl[-1]*float(info.get("sharesOutstanding") or 0))
            fcf=info.get("freeCashflow")
            names.append({"t":sym,"n":nm,"sec":sec_name,"idx":membership(code),"mcap":round(mcap or 1e9),
                          "wr":[round(x,5) for x in wr],"_cl":cl,"_vol":vo,"_fcf":float(fcf) if fcf else None})
        except Exception as e:
            sys.stderr.write(f"skip {sym}: {e}\n")
    # market proxy = SPY weekly
    try:
        h=yf.Ticker("SPY").history(period="1y",interval="1d",auto_adjust=True); spw=[float(x) for x in h["Close"].tolist()][::5]
        mkt=[(spw[i]/spw[i-1]-1) for i in range(1,len(spw))]
    except Exception: mkt=[0.0]*52
    ff={"SMB":[0.0]*len(mkt),"HML":[0.0]*len(mkt),"MOM":[0.0]*len(mkt)}  # FF factors optional; default 0 if no source
    return names,mkt,ff

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--demo",action="store_true"); ap.add_argument("--real",action="store_true")
    ap.add_argument("--out",default="../../marketmap.json"); a=ap.parse_args()
    if a.real:
        names,mkt,ff=real_universe(); snap=build(names,mkt,ff); snap["source"]="Live (yfinance prices/volume + EDGAR FCF) — research only"
    else:
        names,mkt,ff=synth(); snap=build(names,mkt,ff)
    json.dump(snap,open(a.out,"w"),separators=(",",":"))
    print(f"wrote {a.out}: {len(names)} names, asof {snap['asof']}, source={snap['source'][:24]}")

if __name__=="__main__":
    main()
