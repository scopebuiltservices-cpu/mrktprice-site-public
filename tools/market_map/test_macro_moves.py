#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_moves as MM
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
# planted: copper up a clean +2 sigma last week
wr=[0.0]*20+[0.02]; # last week +2% ; std of mostly-zeros tiny -> big sigma; use varied series
import random
random.seed(1); wr=[random.gauss(0,0.01) for _ in range(40)]; wr[-1]=0.02   # ~2% vs ~1% vol => ~2 sigma
ms={"commodities":{"HGUSD":{"name":"Copper Futures","label":"COPPER","last":4.5,"wr":wr}},
    "treasury":{"series":{"10Y":[["d%d"%i, round(4.0+0.01*i+random.gauss(0,0.015),3)] for i in range(30)]}}}
mv=MM.compute(ms, recent=1)
cu=MM.lookup("Copper", mv)
ok("copper resolves by human name", cu is not None and cu["label"]=="COPPER", cu)
ok("copper move +2%% ~ +2 sigma", abs(cu["movePct"]-2.0)<0.5 and cu["sigma"]>1.0, cu)
ok("resolves by label too", MM.lookup("COPPER", mv) is not None)
r=MM.lookup("10Y yield", mv)
ok("rate move from treasury levels", r is not None and r["last"] is not None, r)
ok("rate rising -> positive sigma (noisy series)", r["sigma"]>0, r)
ok("unknown driver -> None", MM.lookup("Plutonium", mv) is None)
# implied contribution math: sens(%/sigma) x sigma
sens=1.42; implied=round(sens*cu["sigma"],2)
ok("implied contribution computes", isinstance(implied,float))
# degenerate (flat) series must NOT blow up sigma
flat={"commodities":{},"treasury":{"series":{"10Y":[["d%d"%i, 4.0+0.011*i] for i in range(30)]}}}
fr=MM.lookup("10Y yield", MM.compute(flat))
ok("degenerate rate series -> sigma clamped", fr is not None and abs(fr["sigma"])<=8.0, fr)
print("\n"+("ALL MACRO-MOVES TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
