#!/usr/bin/env python3
"""Planted-structure tests for quarterly_timeline.py (quarterly stock-timeline spec computation core).
Run: python3 test_quarterly_timeline.py"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quarterly_timeline as q
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
rng=random.Random(7)

# total-return index includes dividends (TR > price-only when a dividend is paid)
cl=[100,101,102,103,104]
tr_nodiv=q.total_return_index(cl); tr_div=q.total_return_index(cl, {2:1.0})
ok("TR index base 100", abs(tr_nodiv[0]-100)<1e-9)
ok("TR with dividend exceeds price-only TR", tr_div[-1] > tr_nodiv[-1], (tr_div[-1],tr_nodiv[-1]))
ok("price-only TR matches normalized price", abs(tr_nodiv[-1]-q.normalized(cl)[-1])<1e-6)

# normalized + relative strength
rs=q.relative_strength([100,110,121],[100,105,110.25])
ok("RS positive when stock outperforms", rs["RS"][-1]>0, rs["RS"][-1])

# drawdown + recovery on a known path: up to 120, down to 90 (-25%), back above 120
path=[100,110,120,100,90,100,115,125]
dd=q.drawdowns(path)
ok("max drawdown = -25%", abs(dd["maxDD"]-(90/120-1))<1e-9, dd["maxDD"])
ok("one completed drawdown episode with recovery", len(dd["episodes"])>=1 and dd["episodes"][0]["recoveryDays"] is not None, dd["episodes"])

# realized vs downside vol
r=[0.01,-0.02,0.015,-0.03,0.02,-0.01,0.005]
ok("realized vol annualized > 0", q.realized_vol(r)>0)
ok("downside vol <= realized vol", q.downside_vol(r) <= q.realized_vol(r)+1e-9)

# market-model beta recovers planted beta 1.5
rm=[0.01*rng.gauss(0,1) for _ in range(300)]
rs_=[1.5*rm[i]+0.004*rng.gauss(0,1) for i in range(300)]
bm=q.beta_market_model(rs_, rm)
ok("beta ~ 1.5", abs(bm["beta"]-1.5)<0.05, bm["beta"])
ok("beta t-stat large (HAC)", bm["t_beta"]>5, bm["t_beta"])
ok("alpha ~ 0", abs(bm["alpha"])<0.01, bm["alpha"])

# relative volume: median-based, spike detected
vol=[100]*25+[300]
rv=q.relative_volume(vol,20)
ok("relative volume spike ~3x", abs(rv[-1]-3.0)<1e-9, rv[-1])
ok("relative volume None before window", rv[0] is None)

# fundamentals
ok("FCF = CFO - capex", q.fcf(100,30)==70)
ok("cash conversion FCF/NI", abs(q.cash_conversion(70,50)-1.4)<1e-9)
ok("net debt = debt - cash", q.net_debt(200,50)==150)
ok("EV identity", q.enterprise_value(1000,200,0,0,50)==1150)
ok("P/E", abs(q.pe(100,5)-20)<1e-9)
ok("EV/EBITDA", abs(q.ev_ebitda(1150,115)-10)<1e-9)
ok("FCF yield", abs(q.fcf_yield(70,1000)-0.07)<1e-9)
ok("YoY growth", abs(q.yoy(120,100)-0.20)<1e-9)
ok("dilution rate", abs(q.dilution(105,100)-0.05)<1e-9)

# surprises
ok("EPS surprise +10%", abs(q.surprise(1.1,1.0)-0.10)<1e-9)
ok("negative surprise", q.surprise(0.9,1.0)<0)
ok("guidance surprise", abs(q.guidance_surprise(11,10)-0.10)<1e-9)

# event study: plant a +2% abnormal jump on the event day
N=400; rm2=[0.008*rng.gauss(0,1) for _ in range(N)]
rsE=[1.2*rm2[i]+0.003*rng.gauss(0,1) for i in range(N)]
ev=300; rsE[ev]+=0.02                                   # +2% abnormal return on event day
es=q.event_study(rsE, rm2, ev)
ok("event study returns alpha/beta", es and abs(es["beta"]-1.2)<0.1, es and es["beta"])
ok("AR on event day ~ +2%", abs(es["AR_event"]-0.02)<0.01, es["AR_event"])
ok("CAR[-1,+1] captures the jump (>1%)", es["CAR"]["-1,1"]>0.01, es["CAR"]["-1,1"])
# CAR significance across several planted events
cars=[0.02,0.018,0.025,0.015,0.022,0.019]
cs=q.car_significance(cars)
ok("CAR mean significant (t>2)", cs["t"]>2 and cs["meanCAR"]>0, cs)
ok("BMO maps to same session, AMC to next", q.map_event_session("BMO")==0 and q.map_event_session("AMC")==1)

# seasonality: plant a strong Q4 effect
qidx=[((i)%4)+1 for i in range(24)]
xq=[10 + (3 if qidx[i]==4 else 0) + 0.2*rng.gauss(0,1) for i in range(24)]
seas=q.quarter_dummy_seasonality(xq, qidx)
ok("Q4 dummy ~ +3", abs(seas["q4"]-3.0)<0.4, seas["q4"])
ok("Q4 effect significant (t>3)", seas["t"]["q4"]>3, seas["t"]["q4"])
ok("Q2/Q3 effects ~ 0", abs(seas["q2"])<0.5 and abs(seas["q3"])<0.5, (seas["q2"],seas["q3"]))

# EWMA overlay smooths but tracks
ew=q.ewma_overlay([1,2,3,4,5,6],20)
ok("EWMA overlay length matches + monotone up on rising input", len(ew)==6 and ew[-1]>ew[0])

# return decomposition
rd=q.return_decomposition(100,120, 5,5.5, 2.0)
ok("decomposition: fundamental growth = EPS growth 10%", abs(rd["fundamentalGrowth"]-0.10)<1e-9, rd)
ok("decomposition: distributions = 2%", abs(rd["distributions"]-0.02)<1e-9)

print("\n"+("ALL QUARTERLY-TIMELINE TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
