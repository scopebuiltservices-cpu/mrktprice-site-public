import flow_keyless as FK
F=[]
def chk(n,c):
    print(("  PASS  " if c else "  FAIL  ")+n)
    if not c: F.append(n)
r=FK.flow_from_13f({"dShares":12.0,"dHolders":5,"holders":300,"shares":1e9})
chk("maps dShares -> net3m fraction", abs(r["net3m"]-0.12)<1e-9)
chk("net1m = net3m/3 monthly proxy", abs(r["net1m"]-0.04)<1e-9)
chk("carries breadth + source", r["dHolders"]==5 and r["holders"]==300 and r["src"]=="SEC 13F")
chk("negative flow (distribution)", FK.flow_from_13f({"dShares":-8.0})["net3m"]==-0.08)
chk("clamps absurd QoQ (+500%)", FK.flow_from_13f({"dShares":500.0})["net3m"]==1.0)
chk("None when no record", FK.flow_from_13f(None) is None and FK.flow_from_13f({}) is None)
chk("None when dShares missing", FK.flow_from_13f({"shares":1e9,"holders":10}) is None)
print("\n"+("ALL FLOW-KEYLESS TESTS PASSED" if not F else "FAILED: %s"%F)); import sys; sys.exit(1 if F else 0)
