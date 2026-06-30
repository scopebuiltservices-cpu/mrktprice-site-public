#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_engine as RE
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)

def mk(t,sec,idx,ret3m,tot,proj,net,sr=0.0):
    return {"t":t,"n":t+" Inc","sec":sec,"idx":idx,"mcap":1000,"beta":1.1,
            "ret":{"1m":ret3m/3,"3m":ret3m,"6m":ret3m*1.5,"12m":ret3m*2},
            "tot":tot,"secRel":sr,
            "z":{"ema":0.5,"mom":0.3,"val":-0.1,"size":0.2,"fcf":0.0,"flow":0.4,"disloc":-0.2,"mfi":0.1,"contra":0.0},
            "pj":{"projClose":110,"projPct":proj,"probUp":0.6,"sigmaHPct":8,"h":21},
            "fund":{"pe":22,"targetUpsidePct":12,"rating":"B+","roe":0.25},
            "mb":{"OIL":0.3,"RATE":-0.4,"DXY":0.1},
            "cr":{"squeeze":False},"reg":{"state":0},
            "news":{"net":net,"label":("tailwind" if net>0.15 else "headwind" if net<-0.15 else "mixed/neutral"),
                    "n":2,"topPos":["good news"] if net>0 else [],"topNeg":["bad news"] if net<0 else []}}

mm={"asof":"2026-06-28",
    "sectors":["Technology","Energy"],
    "sectorCorr":{"order":["Technology","Energy"],"m":[[1.0,-0.3],[-0.3,1.0]]},
    "newsTone":{"market":{"net":0.2,"label":"tailwind","n":3},
                "sectors":{"Technology":{"net":0.3,"label":"tailwind","n":2},"Energy":{"net":-0.2,"label":"headwind","n":1}}},
    "names":[mk("AAA","Technology",["NDX","SPX"],8,0.5,3.0,0.4,1.2),
             mk("BBB","Technology",["NDX"],2,0.1,1.0,-0.3,-0.5),
             mk("CCC","Energy",["SPX"],-3,-0.4,-1.0,-0.4,-1.0),
             {"t":"FX1","sec":"FX","idx":["FACTOR"]}]}  # non-equity, must be excluded

mr=RE.macro_report(mm)
ok("macro excludes non-equity",mr["universe"]==3,mr["universe"])
ok("macro has indices",any(i["index"]=="S&P 500" for i in mr["indices"]))
ok("rotation ranked, tech in",mr["rotation"][0]["sector"]=="Technology" and mr["rotation"][0]["label"]=="rotating in",mr["rotation"][0])
ok("macro drivers surfaced",len(mr["macroDrivers"])>=1)
ok("tailwinds + headwinds split",len(mr["topTailwinds"])>=1 and len(mr["topHeadwinds"])>=1)
ok("market news tone",mr["newsTone"]["label"]=="tailwind")

sr=RE.sector_report(mm,"Technology")
ok("sector counts equities",sr["n"]==2,sr["n"])
ok("sector factor profile",abs(sr["factorProfile"]["ema"]["z"]-0.5)<1e-6)
ok("sector leaders ranked",sr["leaders"][0]["t"]=="AAA")
ok("push-pull peers (Energy negative)",any(p["sector"]=="Energy" for p in sr["pushPull"]["movesWith"]+sr["pushPull"]["movesAgainst"]))
ok("sector news tone",sr["newsTone"]["label"]=="tailwind")

cr=RE.company_report(mm,"AAA")
ok("company found",cr["found"] and cr["ticker"]=="AAA")
ok("role-in-sector rank #1 of 2",cr["roleInSector"]["rankInSector"]==1 and cr["roleInSector"]["ofN"]==2,cr["roleInSector"])
ok("projection present",cr["projection"]["projPct"]==3.0)
ok("macro tilt sorted by |beta|",cr["macroTilt"][0]["driver"]=="RATE",cr["macroTilt"][0])
ok("winds narrative built",len(cr["winds"])>=3)
ok("verdict constructive",cr["verdict"]["tag"]=="constructive",cr["verdict"])
ok("missing company handled",RE.company_report(mm,"ZZZ")["found"]==False)

print("\n"+("ALL REPORT-ENGINE TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
