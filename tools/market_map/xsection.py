"""Server-side full-universe cross-sectional metric matrix (pure stdlib math).
Emits, for the whole universe in one nightly batch: per-ticker top correlations, lead-lag vs the
market, relative-strength rank, rolling beta to market, and INTEREST-RATE-REGIME betas (market
sensitivity when rates are WINDING UP vs UNWINDING). Bounded JSON (top-K per name). Research only."""
from __future__ import annotations
import math, datetime

def _align(series):
    """series: {T:{'dates':[...],'closes':[...]}} -> (tickers, common_dates, {T:[logret]})."""
    cnt={}; pos={}
    for t,s in series.items():
        ds=s.get("dates") or []; cs=s.get("closes") or []
        pos[t]={}
        for i,d in enumerate(ds):
            d=str(d)[:10]; cnt[d]=cnt.get(d,0)+1; 
            if i<len(cs): pos[t][d]=cs[i]
    need=len(series); common=sorted([d for d,c in cnt.items() if c==need])
    if len(common)<20: return None
    R={}
    for t in series:
        a=[]
        for m in range(1,len(common)):
            c0=pos[t].get(common[m-1]); c1=pos[t].get(common[m])
            a.append(math.log(c1/c0) if (c0 and c1 and c0>0 and c1>0) else 0.0)
        R[t]=a
    return list(series.keys()), common[1:], R

def _pearson(a,b):
    n=min(len(a),len(b))
    if n<8: return 0.0
    ma=sum(a[:n])/n; mb=sum(b[:n])/n; sab=saa=sbb=0.0
    for i in range(n):
        da=a[i]-ma; db=b[i]-mb; sab+=da*db; saa+=da*da; sbb+=db*db
    d=math.sqrt(saa*sbb); return (sab/d) if d>0 else 0.0

def _leadlag(a,b,maxlag=5):
    best=(0,_pearson(a,b))
    for L in range(1,maxlag+1):
        c1=_pearson(a[:len(a)-L], b[L:])     # a leads b by L
        c2=_pearson(a[L:], b[:len(b)-L])     # b leads a by L
        if abs(c1)>abs(best[1]): best=(L,c1)
        if abs(c2)>abs(best[1]): best=(-L,c2)
    return best

def _beta(asset,mkt):
    n=min(len(asset),len(mkt))
    if n<8: return None
    mm=sum(mkt[:n])/n; ma=sum(asset[:n])/n; sam=smm=0.0
    for i in range(n):
        dm=mkt[i]-mm; sam+=(asset[i]-ma)*dm; smm+=dm*dm
    return (sam/smm) if smm>0 else None

def _mask_beta(asset,mkt,mask,sign):
    a=[asset[i] for i in range(min(len(asset),len(mask))) if mask[i]==sign]
    m=[mkt[i] for i in range(min(len(mkt),len(mask))) if mask[i]==sign]
    return _beta(a,m) if len(a)>=8 else None

def _rate_regime(rret,win=20):
    m=[]
    for i in range(len(rret)):
        j=max(0,i-win+1); s=sum(rret[j:i+1]); m.append(1 if s>0 else (-1 if s<0 else 0))
    return m

def build_matrix(series, market=None, rate=None, topk=10, maxlag=5):
    al=_align(series)
    if not al: return {"error":"need>=20 common dates","asof":datetime.date.today().isoformat()}
    tickers,dates,R=al
    # benchmark returns: explicit market, else equal-weight universe
    if market and market in R: bR=R[market]
    else:
        n=len(dates); bR=[]
        for i in range(n):
            vals=[R[t][i] for t in tickers]; bR.append(sum(vals)/len(vals) if vals else 0.0)
    mask = _rate_regime(R[rate],20) if (rate and rate in R) else None
    # relative strength
    cum={t:sum(R[t]) for t in tickers}
    rank={t:i+1 for i,t in enumerate(sorted(tickers,key=lambda x:-cum[x]))}
    out={"asof":datetime.date.today().isoformat(),"n":len(dates),"tickers":len(tickers),
         "market":market or "(equal-weight)","rate":rate,"regimeNow":(mask[-1] if mask else 0),"names":{}}
    for t in tickers:
        if t in (market,rate): continue
        fa=R[t]
        cors=sorted([(u,_pearson(fa,R[u])) for u in tickers if u!=t and u not in (market,rate)],
                    key=lambda kv:-abs(kv[1]))[:topk]
        lag,lc=_leadlag(fa,bR,maxlag)   # does the stock lead/lag the market
        rec={"rsRank":rank.get(t),"betaMkt":_beta(fa,bR),"leadMktLag":lag,"leadMktCorr":round(lc,3),
             "topCorr":[{"t":u,"c":round(c,3)} for u,c in cors]}
        if mask is not None:
            rec["betaUp"]=_mask_beta(fa,bR,mask,1); rec["betaDn"]=_mask_beta(fa,bR,mask,-1)
        out["names"][t]=rec
    return out

def _ret(cl):
    return [math.log(cl[i]/cl[i-1]) if (cl[i-1]>0 and cl[i]>0) else 0.0 for i in range(1,len(cl))]

def build_from_closes(closes_map, market_closes=None, rate_closes=None, topk=10, maxlag=5, cap=760):
    """Index/tail-aligned full-universe matrix from {ticker: closes[]} (batched series end together).
    Returns bounded JSON: per-ticker top correlations, lead-lag vs market, RS rank, beta, rate-regime betas."""
    valid={t:c for t,c in closes_map.items() if c and len(c)>=40}
    if len(valid)<3: return {"error":"need>=3 series","asof":datetime.date.today().isoformat()}
    L=min(min(len(c) for c in valid.values()), cap)
    R={t:_ret(c[-L:]) for t,c in valid.items()}; tickers=list(R.keys()); n=L-1
    if market_closes and len(market_closes)>=L: bR=_ret(market_closes[-L:])
    else: bR=[sum(R[t][i] for t in tickers)/len(tickers) for i in range(n)]
    mask=_rate_regime(_ret(rate_closes[-L:]),20) if (rate_closes and len(rate_closes)>=L) else None
    cum={t:sum(R[t]) for t in tickers}; rank={t:i+1 for i,t in enumerate(sorted(tickers,key=lambda x:-cum[x]))}
    out={"asof":datetime.date.today().isoformat(),"n":n,"tickers":len(tickers),
         "market":"index" if market_closes else "(equal-weight)","regimeNow":(mask[-1] if mask else 0),"names":{}}
    for t in tickers:
        fa=R[t]
        cors=sorted([(u,_pearson(fa,R[u])) for u in tickers if u!=t], key=lambda kv:-abs(kv[1]))[:topk]
        lag,lc=_leadlag(fa,bR,maxlag)
        rec={"rsRank":rank[t],"betaMkt":(round(_beta(fa,bR),3) if _beta(fa,bR) is not None else None),
             "leadMktLag":lag,"leadMktCorr":round(lc,3),"topCorr":[{"t":u,"c":round(c,3)} for u,c in cors]}
        if mask is not None:
            bu=_mask_beta(fa,bR,mask,1); bd=_mask_beta(fa,bR,mask,-1)
            rec["betaUp"]=(round(bu,3) if bu is not None else None); rec["betaDn"]=(round(bd,3) if bd is not None else None)
        out["names"][t]=rec
    return out
