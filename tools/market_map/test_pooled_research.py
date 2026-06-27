#!/usr/bin/env python3
"""Planted-structure tests for pooled_research.py (4 methodological gaps + 5 canonical calcs).
Run: python3 test_pooled_research.py"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pooled_research as pr
F=[]
def ok(n,c,d=""):
    print(("  PASS  " if c else "  FAIL  ")+n+("" if c else "  -> "+str(d)))
    if not c: F.append(n)
rng=random.Random(7)

# ===== GAP 1: cross-sectional standardization removes scale-mixing =====
# Name A: strong POSITIVE signal->return, big returns. Name B: NEGATIVE relation, small returns.
sigA=[i for i in range(40)]; retA=[ 0.10*i+0.01*rng.gauss(0,1) for i in range(40)]   # + relation, loud
sigB=[i for i in range(40)]; retB=[-0.002*i+0.0005*rng.gauss(0,1) for i in range(40)] # - relation, quiet
naive_x=sigA+sigB; naive_y=retA+retB
naive_corr=pr._pearson(naive_x,naive_y)
ps,prr=pr.pool_standardized([(sigA,retA),(sigB,retB)],"z")
std_corr=pr._pearson(ps,prr)
ok("naive pooled corr misleadingly positive (loud name dominates)", naive_corr>0.35, naive_corr)
ok("standardized pooling reveals the disagreement (~0)", abs(std_corr)<0.25, std_corr)
ok("standardize is scale-invariant", pr.standardize([1,2,3,4])==pr.standardize([10,20,30,40]))

# ===== GAP 2: HAC / overlapping forward returns =====
# Build overlapping 10-day forward returns from an iid daily series (no real predictability from a lagged x).
n=400; daily=[rng.gauss(0,1) for _ in range(n)]; H=10
fwd=[sum(daily[i+1:i+1+H]) for i in range(n-H)]            # overlapping -> autocorrelated
x=[daily[i] for i in range(n-H)]
naive=pr._pearson(x,fwd)
hs=pr.hac_slope(x,fwd,maxlags=H-1)
ok("hac_slope returns n_eff < n for overlap", hs["n_eff"]<hs["n"], (hs["n_eff"],hs["n"]))
ok("no real edge -> HAC t small despite overlap", abs(hs["t"])<2.5, hs["t"])
# positive autocorrelation inflates the naive (iid) SE understatement: NW LRV > iid var
ar=[0.0]; 
for _ in range(300): ar.append(0.6*ar[-1]+rng.gauss(0,1))
lrv=pr.newey_west_lrv(ar,6); iidv=pr._std(ar,0)**2
ok("Newey-West LRV > iid var under autocorrelation", lrv>iidv, (lrv,iidv))

# ===== GAP 3: transaction costs + turnover =====
pos=[1 if i%2==0 else -1 for i in range(200)]             # flips every bar -> turnover 2.0
ret=[0.01*p+0.001*rng.gauss(0,1) for i,p in enumerate(pos)]  # signal pays gross
bt=pr.backtest_net(pos,ret,cost_bps=5)
bt_hi=pr.backtest_net(pos,ret,cost_bps=200)
ok("turnover ~1.995 for alternating positions (first move from flat=1)", abs(bt["turnover"]-1.995)<1e-6, bt["turnover"])
ok("cost reduces net Sharpe below gross", bt["netSharpe"]<bt["grossSharpe"])
ok("high cost flips edge negative", bt_hi["netMean"]<0, bt_hi["netMean"])
ok("breakeven cost reported and positive", bt["breakevenCost_bps"]>0, bt["breakevenCost_bps"])

# ===== GAP 4: confidence intervals on pooled means =====
samp=[0.5+rng.gauss(0,1) for _ in range(500)]
ci=pr.mean_ci(samp); bci=pr.block_bootstrap_ci(samp,block=5,B=500)
ok("normal CI brackets true mean 0.5", ci["lo"]<0.5<ci["hi"], ci)
ok("bootstrap CI brackets true mean 0.5", bci["lo"]<0.5<bci["hi"], bci)
dci=pr.diff_mean_ci([1.0+rng.gauss(0,1) for _ in range(300)],[0.0+rng.gauss(0,1) for _ in range(300)])
ok("diff CI excludes 0 for separated means", dci["lo"]>0, dci)

# ===== build a panel with a PLANTED cross-sectional signal =====
# 60 dates, 30 names. signal[name] predicts that date's forward return with IC>0.
dates=60; names=["N%02d"%i for i in range(30)]
panel_sig=[]; panel_fwd=[]
for t in range(dates):
    sig={}; fwd={}
    base=[rng.gauss(0,1) for _ in names]
    for j,nm in enumerate(names):
        sig[nm]=base[j]
        fwd[nm]=0.02*base[j]+0.01*rng.gauss(0,1)   # monotone in signal
    panel_sig.append(sig); panel_fwd.append(fwd)

# ===== CANONICAL 5: rank-IC =====
ics,br=pr.rank_ic_series(panel_sig,panel_fwd); ic=pr.ic_summary(ics,br)
ok("mean rank-IC positive on planted signal", ic["meanIC"]>0.2, ic["meanIC"])
ok("IC Newey-West t is significant", ic["icT"]>3, ic["icT"])
ok("breadth ~30 and IR_law computed", abs(ic["breadth"]-30)<1e-9 and ic["IR_law"]>0, ic)

# ===== CANONICAL 6: long-short quantile + monotonicity =====
ls=pr.quantile_ls(panel_sig,panel_fwd,q=5)
ok("top-minus-bottom LS mean positive", ls["lsMean"]>0, ls["lsMean"])
ok("LS t significant", ls["lsT"]>3, ls["lsT"])
ok("bucket means monotone in signal", ls["monotonicity"]>0.9, ls["monotonicity"])

# ===== CANONICAL 7: regime-conditioned edge (edge ONLY in regime 0) =====
N=600; sig=[rng.gauss(0,1) for _ in range(N)]; reg=[0 if i%2==0 else 1 for i in range(N)]
fwd=[ (0.03*sig[i] if reg[i]==0 else 0.0) + 0.01*rng.gauss(0,1) for i in range(N)]
re=pr.regime_edge(sig,fwd,reg)
ok("edge present in calm regime 0", re["byRegime"][0]["ic"]>0.2, re["byRegime"][0])
ok("edge absent in stress regime 1", abs(re["byRegime"][1]["ic"])<0.12, re["byRegime"][1])
ok("IC spread calm-minus-stress positive", re["icSpread"]>0.1, re["icSpread"])

# ===== CANONICAL 8: correlation shrinkage / EWMA / significance =====
# 3 names: two highly correlated, one independent.
base=[rng.gauss(0,1) for _ in range(200)]
rets={"A":[b+0.1*rng.gauss(0,1) for b in base],
      "B":[b+0.1*rng.gauss(0,1) for b in base],
      "C":[rng.gauss(0,1) for _ in range(200)]}
nm,C=pr.sample_corr(rets); nm2,S,delta=pr.ledoit_wolf_constant_corr(rets)
iA,iB=nm.index("A"),nm.index("B")
ok("sample corr A-B high", C[iA][iB]>0.9, C[iA][iB])
ok("LW shrinks A-B toward the mean (lower than sample)", S[iA][iB]<C[iA][iB], (S[iA][iB],C[iA][iB]))
ok("LW intensity in [0,1]", 0.0<=delta<=1.0, delta)
nm3,E=pr.ewma_corr(rets,0.94)
ok("EWMA corr A-B high too", E[nm3.index("A")][nm3.index("B")]>0.8, E[nm3.index("A")][nm3.index("B")])
ok("corr_pvalue tiny for strong corr", pr.corr_pvalue(C[iA][iB],200)<1e-6, pr.corr_pvalue(C[iA][iB],200))
ok("corr_pvalue large for ~0 corr", pr.corr_pvalue(0.02,200)>0.5, pr.corr_pvalue(0.02,200))

# ===== CANONICAL 9: Fama-MacBeth recovers planted risk premium =====
# per date: y = 0.5 + 1.5*f1 - 0.8*f2 + noise across names
pX=[]; pY=[]
for t in range(80):
    X={}; Y={}
    for nm_ in names:
        f1=rng.gauss(0,1); f2=rng.gauss(0,1)
        X[nm_]=[f1,f2]; Y[nm_]=0.5+1.5*f1-0.8*f2+0.2*rng.gauss(0,1)
    pX.append(X); pY.append(Y)
fm=pr.fama_macbeth(pX,pY)
ok("FM lambda1 ~ 1.5", abs(fm["lambdas"][0]["coef"]-1.5)<0.15, fm["lambdas"][0])
ok("FM lambda2 ~ -0.8", abs(fm["lambdas"][1]["coef"]+0.8)<0.15, fm["lambdas"][1])
ok("FM lambda1 t large", fm["lambdas"][0]["t"]>5, fm["lambdas"][0]["t"])
ok("FM intercept ~ 0.5", abs(fm["intercept"]["coef"]-0.5)<0.15, fm["intercept"])

print("\n"+("ALL POOLED-RESEARCH TESTS PASSED" if not F else "%d FAILED: %s"%(len(F),F)))
raise SystemExit(1 if F else 0)
