"""Free short-pressure / squeeze signal from the SEC fails-to-deliver files (already used for the CUSIP map).
Aggregates recent fails per ticker and the trend vs the prior half-month. No key. Research only."""
import io, zipfile, datetime as dt
FTD_BASE="https://www.sec.gov/files/data/fails-deliver-data"
UA={"User-Agent":"MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}
def parse_fails(text_iter):
    """SEC FTD pipe rows DATE|CUSIP|SYMBOL|QTY|DESCRIPTION|PRICE -> {ticker: total_fail_qty}."""
    out={}
    for line in text_iter:
        p=line.split("|")
        if len(p)<4: continue
        sym=p[2].strip().upper()
        if not sym or sym=="SYMBOL": continue
        try: q=float(p[3])
        except Exception: continue
        out[sym]=out.get(sym,0.0)+q
    return out
def _half_labels(today=None):
    today=today or dt.date.today(); labs=[]
    for back in range(0,4):
        y,m=today.year,today.month-back
        while m<=0: m+=12; y-=1
        labs.append("%d%02db"%(y,m)); labs.append("%d%02da"%(y,m))
    return labs
def fetch_squeeze(tickers, sess=None):
    """Returns {ticker: {fails, prevFails, trend, level}} from the latest two FTD files. Free."""
    try:
        import requests
        s=sess or requests.Session(); want={t.upper() for t in tickers}
        snaps=[]
        for lab in _half_labels():
            try:
                r=s.get("%s/cnsfails%s.zip"%(FTD_BASE,lab),headers=UA,timeout=120)
                if r.status_code!=200 or len(r.content)<500: continue
                zf=zipfile.ZipFile(io.BytesIO(r.content)); nm=zf.namelist()[0]
                agg=parse_fails(io.TextIOWrapper(zf.open(nm),encoding="latin-1",errors="replace"))
                snaps.append({t:agg.get(t,0.0) for t in want})
                if len(snaps)>=2: break
            except Exception: continue
        if not snaps: return {}
        cur=snaps[0]; prev=snaps[1] if len(snaps)>1 else {}
        out={}
        for t in want:
            f=cur.get(t,0.0); pf=prev.get(t,0.0)
            if f<=0 and pf<=0: continue
            trend=("rising" if f>pf*1.25 else "falling" if f<pf*0.8 else "flat")
            out[t]={"fails":int(f),"prevFails":int(pf),"trend":trend,
                    "level":("elevated" if f>=500000 else "moderate" if f>=100000 else "low")}
        return out
    except Exception:
        return {}
