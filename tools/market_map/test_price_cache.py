import price_cache as P
F=[]
def chk(n,c):
    print(("  PASS  " if c else "  FAIL  ")+n)
    if not c: F.append(n)
# fetch_plan
chk("short cache -> full", P.fetch_plan({"dates":["2025-01-01"]*5}, "2025-06-01")==("full",None))
cur={"dates":[ "2025-05-%02d"%d for d in range(1,32) ]}  # 31 dates
chk("current cache -> none", P.fetch_plan(cur, cur["dates"][-1])[0]=="none")
chk("small gap -> delta since last", P.fetch_plan(cur, "2025-06-03")==("delta","2025-05-31"))
chk("huge gap -> full", P.fetch_plan(cur, "2025-12-31")==("full",None))
# merge_bars: dedup overlap + append new + sorted
cached={"dates":["2025-05-01","2025-05-02"],"cl":[10,11],"vo":[1,1],"hi":[10,11],"lo":[10,11]}
fresh ={"dates":["2025-05-02","2025-05-03"],"cl":[11,12],"vo":[1,1],"hi":[11,12],"lo":[11,12]}
m=P.merge_bars(cached,fresh)
chk("merge dedups + appends", m["dates"]==["2025-05-01","2025-05-02","2025-05-03"] and m["cl"]==[10,11,12])
chk("merge sorts", m["dates"]==sorted(m["dates"]))
# concurrent_fetch maps all + isolates failures
def getter(s):
    if s=="BAD": raise ValueError("boom")
    return s.lower()
r=P.concurrent_fetch(["AAA","BBB","BAD","CCC"], getter, workers=4)
chk("concurrent maps all symbols", set(r.keys())=={"AAA","BBB","BAD","CCC"})
chk("concurrent isolates failure", r["BAD"] is None and r["AAA"]=="aaa")
chk("last_cached_date", P.last_cached_date(cached)=="2025-05-02" and P.last_cached_date(None) is None)
print("\n"+("ALL PRICE-CACHE TESTS PASSED" if not F else "FAILED: %s"%F))
import sys; sys.exit(1 if F else 0)
