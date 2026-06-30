#!/usr/bin/env python3
import os, sys, html.parser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_engine as RE, report_render as RR
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
def mk(t,sec,idx,ret3m,tot,proj,net,sr=0.0):
    return {"t":t,"n":t+" Inc","sec":sec,"idx":idx,"mcap":1000,"beta":1.1,
            "ret":{"1m":ret3m/3,"3m":ret3m,"6m":ret3m*1.5,"12m":ret3m*2},"tot":tot,"secRel":sr,
            "z":{"ema":0.5,"mom":0.3,"val":-0.1,"size":0.2,"fcf":0.0,"flow":0.4,"disloc":-0.2,"mfi":0.1,"contra":0.0},
            "pj":{"projPct":proj,"probUp":0.6,"sigmaHPct":8,"h":21},"fund":{"pe":22,"targetUpsidePct":12,"rating":"B+","roe":0.25},
            "mb":{"OIL":0.3,"RATE":-0.4},"news":{"net":net,"label":("tailwind" if net>0.15 else "headwind" if net<-0.15 else "mixed/neutral"),"n":2,"topPos":["good"] if net>0 else [],"topNeg":["bad"] if net<0 else []}}
mm={"asof":"2026-06-28","sectors":["Technology","Energy"],"sectorCorr":{"order":["Technology","Energy"],"m":[[1,-0.3],[-0.3,1]]},
    "newsTone":{"market":{"net":0.2,"label":"tailwind","n":3},"sectors":{"Technology":{"net":0.3,"label":"tailwind","n":2},"Energy":{"net":-0.2,"label":"headwind","n":1}}},
    "names":[mk("AAA","Technology",["NDX","SPX"],8,0.5,3.0,0.4,1.2),mk("BBB","Technology",["NDX"],2,0.1,1.0,-0.3,-0.5),mk("CCC","Energy",["SPX"],-3,-0.4,-1.0,-0.4,-1.0)]}

class V(html.parser.HTMLParser):
    def error(self,m): raise ValueError(m)
def valid_html(s):
    V().feed(s); return True

for name, fn in [("macro",RR.render_macro(RE.macro_report(mm))),
                 ("sector",RR.render_sector(RE.sector_report(mm,"Technology"))),
                 ("company",RR.render_company(RE.company_report(mm,"AAA")))]:
    ok("%s renders valid HTML"%name, valid_html(fn))
    ok("%s has DOCTYPE+svg tiles"%name, fn.startswith("<!DOCTYPE html>") and "<svg" in fn)
    ok("%s print CSS present"%name, "@media print" in fn)
ok("macro shows rotation table","Sector rotation" in RR.render_macro(RE.macro_report(mm)))
ok("company shows winds","Headwinds" in RR.render_company(RE.company_report(mm,"AAA")))
ok("sentiment bar svg", "<circle" in RR.sentiment_bar(0.4))
print("\n"+("ALL REPORT-RENDER TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
