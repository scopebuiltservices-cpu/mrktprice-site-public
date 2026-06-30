#!/usr/bin/env python3
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_engine as RE
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
NEXT=(dt.date.today()+dt.timedelta(days=10)).isoformat()
PAST=(dt.date.today()-dt.timedelta(days=80)).isoformat()
def mk(t,sec,idx,ret3m,tot,proj,net,sr=0.0):
    return {"t":t,"n":t+" Inc","sec":sec,"idx":idx,"mcap":1000,"beta":1.1,
            "ret":{"1m":ret3m/3,"3m":ret3m,"6m":ret3m*1.5,"12m":ret3m*2},"tot":tot,"secRel":sr,
            "z":{"ema":0.5,"mom":0.3,"val":-0.1,"size":0.2,"fcf":0.0,"flow":0.4,"disloc":-0.2,"mfi":0.1,"contra":0.0},
            "pj":{"projPct":proj,"probUp":0.6,"sigmaHPct":8,"h":21},
            "fund":{"pe":22,"targetUpsidePct":12,"rating":"B+","roe":0.25,"ebitdaLastQ":3200,"ebitdaNextQ":3520,"nextExDate":NEXT,"div12m":0.96,"lastSplit":{"date":"2024-06-10","ratio":"10:1"}},
            "mb":{"OIL":0.3,"RATE":-0.4},"macroR2":39,"drv":"RATE",
            "macro3":{"rate":{"f":"10Y yield","sens":-0.27,"corr":-0.08,"pcorr":0.01,"sig":False,"dir":"against","weak":True,"stab":"stable"},
                      "top":[{"f":"Copper","sens":1.2,"corr":0.35,"pcorr":0.31,"sig":True,"dir":"with","stab":"stable"},
                             {"f":"Orange Juice","sens":-0.9,"corr":-0.22,"pcorr":-0.18,"sig":False,"dir":"against","stab":"fading"}]},
            "deps":[{"f":"S&P 500","corr":0.59,"pcorr":0.59,"sens":1.99,"sig":True,"dir":"with","stab":"stable"},
                    {"f":sec+" sector","corr":0.53,"pcorr":0.1,"sens":1.78,"sig":True,"dir":"with","stab":"stable"}],
            "earn":{"q":[{"d":PAST,"a":1.6,"e":1.5,"q":2,"y":2026,"s":6.7},{"d":NEXT,"a":None,"e":1.72,"q":3,"y":2026}]},
            "reg":{"state":0},
            "news":{"net":net,"label":("tailwind" if net>0.15 else "headwind" if net<-0.15 else "mixed/neutral"),"n":2,"topPos":["good"] if net>0 else [],"topNeg":["bad"] if net<0 else []}}
mm={"asof":"2026-06-28","sectors":["Technology","Energy"],"sectorCorr":{"order":["Technology","Energy"],"m":[[1,-0.3],[-0.3,1]]},
    "macroSeries":{"treasury":{"tenors":{"1M":3.7,"3M":3.83,"6M":3.94,"1Y":3.94,"2Y":4.07,"5Y":4.12,"10Y":4.38,"30Y":4.87},"series":{"10Y":[["d%d"%i,4.0+0.01*i] for i in range(30)]}},"commodities":{"HGUSD":{"name":"Copper Futures","label":"COPPER","last":4.5,"wr":[0.01,-0.01,0.02,-0.005,0.015,-0.008,0.012,-0.004,0.018,-0.006,0.03]}}},
    "_macroEvents":[{"event":"FOMC decision","date":(dt.date.today()+dt.timedelta(days=5)).isoformat(),"detail":"rate decision"}],
    "newsTone":{"market":{"net":0.2,"label":"tailwind","n":3},"sectors":{"Technology":{"net":0.3,"label":"tailwind","n":2},"Energy":{"net":-0.2,"label":"headwind","n":1}}},
    "names":[mk("AAA","Technology",["NDX","SPX"],8,0.5,3.0,0.4,1.2),mk("BBB","Technology",["NDX"],2,0.1,1.0,-0.3,-0.5),mk("CCC","Energy",["SPX"],-3,-0.4,-1.0,-0.4,-1.0)]}

# --- company: new sections ---
c=RE.company_report(mm,"AAA")
ok("EBITDA last+next+growth",c["ebitda"]["lastQAdj"]==3200 and c["ebitda"]["nextQExp"]==3520 and c["ebitda"]["growthPct"]==10.0,c["ebitda"])
cal={r["event"] for r in c["calendar"]}
ok("calendar has earnings+exdiv+split+macro","Next earnings" in cal and "Ex-dividend" in cal and "Last split" in cal and "FOMC decision" in cal,cal)
ok("calendar sorted by date",[r["date"] for r in c["calendar"]]==sorted(r["date"] for r in c["calendar"]))
s=c["sensitivities"]
ok("rate sensitivity (10Y) surfaced",s["rate"]["factor"]=="10Y yield" and s["rate"]["sensPct"]==-0.27,s["rate"])
ok("commodity sensitivities + wind",any(r["factor"]=="Copper" and r["sensPct"]==1.2 and r["wind"]=="tailwind" for r in s["commodities"]),s["commodities"])
cop=next(r for r in s["commodities"] if r["factor"]=="Copper")
ok("live: Copper driverSigma computed",cop.get("driverSigma") is not None,cop)
ok("live: implied %% = sens x sigma",cop.get("impliedPct") is not None and abs(cop["impliedPct"]-round(1.2*cop["driverSigma"],2))<1e-6,cop)
ok("live: total macro contribution",s.get("liveContribPct") is not None and s.get("hasLive"),s.get("liveContribPct"))
ok("market deps (S&P/sector)",any(r["factor"]=="S&P 500" for r in s["market"]))
ok("macroR2 surfaced",s["macroR2"]==39)

# --- macro: 100x sections ---
m=RE.macro_report(mm)
ok("treasury curve points",len(m["treasuryCurve"]["points"])==8 and m["treasuryCurve"]["slope2s10s"]==0.31,m["treasuryCurve"])
ok("macro complex aggregates drivers",len(m["macroComplex"])>=1 and "avgAbsSens" in m["macroComplex"][0],m["macroComplex"][:2])
ok("regime mix",m["regimeMix"]["calm"]>=1)
ok("earnings density next14d",m["earningsAhead"]["next14d"]>=1,m["earningsAhead"])

print("\n"+("ALL REPORT-ENGINE TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
