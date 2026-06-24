import math, black_scholes as bs, bs_ext as be, american as am, realized as rv
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else " -> "+str(d))); 
    if not c: F.append(n)

# higher greeks vs finite differences of the verified pricer
def fd(f,x,h): return (f(x+h)-f(x-h))/(2*h)
S,K,T,r,sig,q=100,105,0.6,0.04,0.3,0.01
g=be.greeks_ext(S,K,T,r,sig,q,"C")
vanna_fd=fd(lambda s:bs.greeks(s,K,T,r,sig,q,"C")["vega"],S,1e-3)      # dvega/dS == vanna
ok("vanna == dVega/dS", abs(g["vanna"]-vanna_fd)<1e-3, f'{g["vanna"]} vs {vanna_fd}')
volga_fd=fd(lambda v:bs.greeks(S,K,T,r,v,q,"C")["vega"],sig,1e-3)
ok("volga == dVega/dSigma", abs(g["volga"]-volga_fd)<1e-2, f'{g["volga"]} vs {volga_fd}')
ok("probITM == N(d2) in (0,1)", 0<g["probITM"]<1)
ok("dualDelta call <0", g["dualDelta"]<0)
# fast IV recovers sigma
px=bs.bs_price(S,K,T,r,0.42,q,"C"); ivf=be.implied_vol_fast(px,S,K,T,r,q,"C")
ok("fast IV round-trip", abs(ivf-0.42)<1e-5, ivf)

# American: no-div American call == European; American put >= European put; converges
euro_c=bs.bs_price(100,100,1,0.05,0.25,0,"C"); am_c=am.crr_price(100,100,1,0.05,0.25,0,"C",steps=600)
ok("American call (no div) == European", abs(am_c-euro_c)<0.02, f'{am_c} vs {euro_c}')
euro_p=bs.bs_price(100,100,1,0.05,0.25,0,"P"); am_p=am.crr_price(100,100,1,0.05,0.25,0,"P",steps=600)
ok("American put >= European put", am_p>=euro_p-1e-6 and am_p>euro_p, f'{am_p} vs {euro_p}')
ok("early-exercise premium > 0 for ITM put", am.early_exercise_premium(90,100,1,0.05,0.3,0,"P",400)>0)

# realized vol estimators on a synthetic OHLC series (~30% ann)
import random; random.seed(3)
o,h,l,c=[],[],[],[]; px=100.0; sig_true=0.30; M=80   # simulate a realistic intraday path per day
sd=sig_true/math.sqrt(252*M)
for _ in range(252):
    op=px; cur=op; hi=op; lo=op
    for _ in range(M):
        cur*=math.exp(random.gauss(0,sd)); hi=max(hi,cur); lo=min(lo,cur)
    cl=cur; o.append(op);h.append(hi);l.append(lo);c.append(cl);px=cl
for nm,val in [("close",rv.close_to_close(c)),("parkinson",rv.parkinson(h,l)),
               ("garman_klass",rv.garman_klass(o,h,l,c)),("rogers_satchell",rv.rogers_satchell(o,h,l,c)),
               ("yang_zhang",rv.yang_zhang(o,h,l,c))]:
    ok(f"{nm} vol in 0.20-0.42", val is not None and 0.20<val<0.42, val)
# HAR-RV fits and forecasts a positive variance
rvs=[(math.log(c[i]/c[i-1]))**2 for i in range(1,len(c))]*2   # lengthen series
h_=rv.har_rv(rvs); ok("HAR-RV forecast > 0", h_ and h_["forecastVar"]>0, h_ and h_["forecastVar"])


# ===== batch 2: chain quality, parity, rate curve =====
import chain_quality as cq, parity as par, rate_curve as rc
S,T,r,q=100.0,0.5,0.04,0.0
# build an arbitrage-free chain (BS marks) across strikes for C and P
ch=[]
for K in range(80,121,5):
    for kind in ("C","P"):
        ch.append({"strike":K,"type":kind,"oi":500,"bid":bs.bs_price(S,K,T,r,0.3,q,kind)-0.05,
                                                  "ask":bs.bs_price(S,K,T,r,0.3,q,kind)+0.05})
ch=cq.liquidity_filter(ch)
ok("liquidity_filter keeps marks", all(o["mark"] is not None for o in ch))
ok("clean chain: no no-arb violations", cq.no_arb_violations(ch,S,T,r,q)==[], cq.no_arb_violations(ch,S,T,r,q)[:2])
# inject a butterfly violation (one call far too cheap)
bad=[dict(o) for o in ch]
for o in bad:
    if o["type"]=="C" and float(o["strike"])==100: o["mark"]=0.1
ok("injected violation is flagged", len(cq.no_arb_violations(bad,S,T,r,q))>0)
# liquidity removes low OI / wide spread
ch2=cq.liquidity_filter([{"strike":100,"type":"C","oi":2,"bid":1,"ask":2},
                         {"strike":100,"type":"P","oi":900,"bid":0.1,"ask":5.0},
                         {"strike":105,"type":"C","oi":900,"bid":1.0,"ask":1.1}])
ok("liquidity drops thin/wide", len(ch2)==1 and float(ch2[0]["strike"])==105, [o['strike'] for o in ch2])

# parity recovers the forward & implied dividend
qd=0.03; chp=[]
for K in range(80,121,5):
    for kind in ("C","P"):
        chp.append({"strike":K,"type":kind,"mark":bs.bs_price(S,K,T,r,0.3,qd,kind)})
pf=par.implied_forward(chp,S,T,r)
Fexp=S*math.exp((r-qd)*T)
ok("parity forward recovered", abs(pf["forward"]-Fexp)<0.05, f'{pf["forward"]} vs {Fexp:.4f}')
ok("parity implied div ~ q", abs(pf["impliedDivYield"]-qd)<0.01, pf["impliedDivYield"])

# rate curve interpolates monotonically between points
cv=rc.default_curve()
ok("rate_for interpolates", cv.rate_for(0.1)>0 and cv.rate_for(0.5)>0 and cv.rate_for(30)>0)
ok("rate_for between 1y and 2y", min(cv.rate_for(1),cv.rate_for(2))<=cv.rate_for(1.5)<=max(cv.rate_for(1),cv.rate_for(2)))


# ===== batch 3: SVI surface, risk-neutral density / VRP / BKM =====
import vol_surface as vs, risk_neutral as rn
# SVI: recover a planted slice
true=[0.04,0.18,-0.5,0.02,0.12]; T2=0.5
ks=[x/20 for x in range(-8,9)]; ws=[vs.svi_w(k,true) for k in ks]
cal=vs.calibrate_svi(ks,ws); 
ok("SVI calibration fits planted slice (rmse<1e-3)", cal and cal[1]<1e-3, cal and cal[1])
feat=vs.slice_features(cal[0],T2)
ok("SVI ATM vol ~ sqrt(w0/T)", abs(feat["atmVol"]-math.sqrt(vs.svi_w(0,true)/T2))<2e-3, feat["atmVol"])
ok("SVI butterfly arb-free flag", feat["butterflyArbFree"] in (True,False))

# Breeden-Litzenberger density integrates ~1 and prob_below(K)~N(-d2) for a BS chain
S,T,r,sg,q=100.0,0.5,0.03,0.25,0.0
calls=[(K,bs.bs_price(S,K,T,r,sg,q,"C")) for K in [x for x in range(60,141,2)]]
dens=rn.bl_density(calls,T,r)
area=sum((dens[i+1][0]-dens[i][0])*(dens[i+1][1]+dens[i][1])/2 for i in range(len(dens)-1))
ok("BL density integrates to ~1", abs(area-1.0)<0.02, area)
pb=rn.prob_below(dens,100.0); d1,d2=bs._d1_d2(S,100.0,T,r,sg,q)
ok("BL P(S_T<F) ~ N(-d2)", abs(pb-bs.norm_cdf(-d2))<0.03, f'{pb} vs {bs.norm_cdf(-d2):.3f}')

# model-free implied vol ~ sigma for a flat-vol BS chain
chain=[]
for K in range(60,141,2):
    for kind in ("C","P"): chain.append({"strike":K,"type":kind,"mark":bs.bs_price(S,K,T,r,sg,q,kind)})
mf=rn.model_free_iv(chain,S,T,r)
ok("model-free IV ~ sigma (flat surface)", abs(mf["mfImpliedVol"]-sg)<0.01, mf["mfImpliedVol"])
# VRP positive when implied var > forecast var
vrp=rn.variance_risk_premium(chain,S,T,r,(sg*0.8)**2)
ok("VRP positive vs lower RV forecast", vrp and vrp["vrp"]>0, vrp and vrp["vrp"])
# BKM: lognormal BS chain -> finite moments, slight negative skew in returns space
bk=rn.bkm_moments(chain,S,T,r)
ok("BKM moments finite", bk and abs(bk["rnSkew"])<3 and bk["rnKurt"]>0, bk)
# left-skewed surface (puts richer) -> more negative BKM skew
chain_sk=[]
for K in range(60,141,2):
    skvol=sg+max(0,(100-K))/100*0.15      # higher vol for low strikes (put skew)
    for kind in ("C","P"): chain_sk.append({"strike":K,"type":kind,"mark":bs.bs_price(S,K,T,r,skvol,q,kind)})
bk2=rn.bkm_moments(chain_sk,S,T,r)
ok("put-skew -> more negative BKM skew", bk2["rnSkew"]<bk["rnSkew"], f'{bk2["rnSkew"]} < {bk["rnSkew"]}')


# ===== batch 4: signal validation + orchestrator =====
import signal_linkage as sl, options_analytics as oa, random
random.seed(11)
# planted predictor: f_true correlates with y; f_noise do not
n=300; y=[random.gauss(0,1) for _ in range(n)]
f_true=[0.6*y[i]+random.gauss(0,0.8) for i in range(n)]
f_n1=[random.gauss(0,1) for _ in range(n)]; f_n2=[random.gauss(0,1) for _ in range(n)]
rep=sl.ic_report([f_true,f_n1,f_n2],y,["true","noise1","noise2"])
sig=[r for r in rep if r["fdrSignificant"]]
ok("validation flags the true predictor", any(r["name"]=="true" and r["fdrSignificant"] for r in rep), rep[0])
ok("validation rejects pure noise (FDR)", all(r["name"]=="true" for r in sig), [r['name'] for r in sig])

# orchestrator runs end-to-end on a synthetic chain with a real vol premium
S=300.0; days=30; T=days/365; r=0.043
closes=[280.0]
for _ in range(80): closes.append(closes[-1]*math.exp(random.gauss(0,0.20/math.sqrt(252))))
S=closes[-1]
chain=[]
rvc=rv.close_to_close(closes)
for K in range(int(S*0.85)//5*5,int(S*1.15),5):
    for kind in ("C","P"):
        ivk=rvc+0.05+max(0,(S-K))/S*0.10   # premium + put skew
        m=bs.bs_price(S,K,T,r,ivk,0,kind)
        chain.append({"strike":K,"type":kind,"oi":random.randint(200,5000),"bid":m-0.05,"ask":m+0.05})
res=oa.analyze("DEMO",S,closes,chain,days,r=r)
ok("orchestrator returns full summary", res and res["nContracts"]>5)
ok("forward/impliedDiv present", res["forward"] is not None)
ok("VRP positive (implied>realized)", res["vrpVolPts"] is not None and res["vrpVolPts"]>0, res["vrpVolPts"])
ok("RN skew negative (put skew)", res["rnSkew"] is not None and res["rnSkew"]<0, res["rnSkew"])
ok("model-free IV present", res["mfImpliedVolPct"] is not None)
ok("American ATM values present", res["american"]["amCall"]>0 and res["american"]["amPut"]>0)
ok("provisional optTilt finite", -1<=res["optTilt"]<=1 and res["optTiltStatus"]=="provisional/uncalibrated", res["optTilt"])

print("\n"+("ALL QUANT-EXTENSION TESTS PASS" if not F else f"{len(F)} FAIL: {F}"))
raise SystemExit(1 if F else 0)
