"""sec_insider.py — SEC EDGAR insider (Form 4) + fiscal-map helpers, extracted from
build_market_map.py to keep the orchestrator under the file-line budget. Pure stdlib + requests.
Public API used by the build: fetch_insider(), _sec_fiscal_map(); _INS_UA is the shared UA."""
import os, sys, re, json, time
import datetime as dt
import requests
import xml.etree.ElementTree as ET

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
