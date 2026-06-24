"""Regression tests for connector resilience: the record-gate + HTTP retry/backoff."""
import os, tempfile, datetime
os.environ["BS_HISTORY"]=os.path.join(tempfile.mkdtemp(),"h.jsonl")   # before bs_record binds
import bs_record as rec, options_analytics as oa, eodhd_options as eo, fmp_connector as fc

_today=datetime.date.today(); _exp=(_today+datetime.timedelta(days=30)).isoformat()
def _chain():
    return [{"strike":100,"type":"C","oi":500,"iv":0.25,"dte":30,"exp":_exp,"bid":3,"ask":3.2,"last":3.1},
            {"strike":100,"type":"P","oi":500,"iv":0.26,"dte":30,"exp":_exp,"bid":2.9,"ask":3.1,"last":3.0},
            {"strike":95,"type":"P","oi":400,"iv":0.27,"dte":30,"exp":_exp,"bid":1.5,"ask":1.7,"last":1.6},
            {"strike":105,"type":"C","oi":400,"iv":0.24,"dte":30,"exp":_exp,"bid":1.4,"ask":1.6,"last":1.5}]

class _Resp:
    def __init__(s,code,p=None,ra=None): s.status_code=code; s._p=p or {}; s.headers={"Retry-After":ra} if ra else {}
    def json(s): return s._p

def t_record_gate():
    h=rec.DEFAULT
    oa.analyze("TST",100,[100]*60,_chain(),30,record=False); a=len(rec.load(h))
    oa.analyze("TST",100,[100]*60,_chain(),30,record=True);  b=len(rec.load(h))
    assert a==0 and b==1, (a,b)
    print("  PASS  record flag gates calibration-history write (False=%d, True=%d)"%(a,b))

def t_eodhd_retry():
    rows=[{"attributes":{"contract":"C1","type":"call","strike":100,"open_interest":500,"volatility":0.25,
           "gamma":0.01,"delta":0.5,"bid":3,"ask":3.2,"exp_date":_exp,"dte":30,"tradetime":_today.isoformat()}}]
    class S:
        def __init__(s): s.calls=0
        def get(s,u,params=None,timeout=None):
            s.calls+=1
            if s.calls==1: return _Resp(429,ra="0")
            off=int((params or {}).get("page[offset]","0")); return _Resp(200,{"data":(rows if off==0 else []),"meta":{"total":1}})
    s=S(); ch,nr=eo._fetch_chain("AAPL","demo",s)
    assert s.calls==2 and len(ch)==1, (s.calls,len(ch))
    print("  PASS  EODHD retries past a 429 then parses (calls=%d)"%s.calls)

def t_fmp_retry():
    os.environ["FMP_API_KEY"]="dummy"
    class S:
        def __init__(s): s.calls=0
        def get(s,u,timeout=None):
            s.calls+=1
            if s.calls==1: return _Resp(503,ra="0")
            if "quote" in u: return _Resp(200,[{"price":201.5,"pe":33.4,"eps":6.0}])
            if "ratios-ttm" in u: return _Resp(200,[{"priceToEarningsRatioTTM":33,"enterpriseValueMultipleTTM":23.4,"priceToEarningsGrowthRatioTTM":2.4}])
            return _Resp(200,[{"epsAvg":7.1}])
    out=fc.fetch("AAPL",sess=S())
    assert out and out["val"]["peg"]==2.4, out
    print("  PASS  FMP retries past a 503 then parses (peg=%s)"%out["val"]["peg"])

if __name__=="__main__":
    t_record_gate(); t_eodhd_retry(); t_fmp_retry()
    print("\nALL CONNECTOR-RESILIENCE TESTS PASS")
