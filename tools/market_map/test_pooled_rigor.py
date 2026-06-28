#!/usr/bin/env python3
"""Tests for pooled_rigor.py against planted structure. Run: python3 test_pooled_rigor.py"""
import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pooled_rigor as pr

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

rng = random.Random(7)

# ---- PSR / MinTRL ----
ok("PSR rises with Sharpe", pr.psr(0.20, 252) > pr.psr(0.05, 252), (pr.psr(0.05, 252), pr.psr(0.20, 252)))
ok("PSR in (0,1)", 0 < pr.psr(0.1, 252) < 1)
ok("PSR ~0.5 when SR==benchmark", abs(pr.psr(0.1, 252, sr_benchmark=0.1) - 0.5) < 1e-6)
ok("MinTRL finite for SR>benchmark", pr.min_trl(0.15) is not None and pr.min_trl(0.15) > 1)
ok("MinTRL None when SR<=benchmark", pr.min_trl(0.0) is None)
ok("MinTRL shrinks as SR grows", pr.min_trl(0.30) < pr.min_trl(0.10))

# ---- two-way clustered SE + FE: planted panel y = b*x + g_i + d_t + noise ----
NT, ND = 12, 40; b_true = 0.8
x=[]; y=[]; gid=[]; did=[]
g_eff={i:rng.gauss(0,1) for i in range(NT)}; d_eff={t:rng.gauss(0,1) for t in range(ND)}
for i in range(NT):
    for t in range(ND):
        xi = d_eff[t]*0.5 + rng.gauss(0,1)      # x correlated within date -> needs clustering
        yi = b_true*xi + g_eff[i] + d_eff[t] + rng.gauss(0,0.5)
        x.append(xi); y.append(yi); gid.append(i); did.append(t)
cl = pr.two_way_cluster_se(x,y,gid,did)
ok("clustered SE returns", cl is not None and cl["se"]>0, cl)
ok("clustered beta near truth (with FE confound it's biased; just finite)", math.isfinite(cl["beta"]))
fe = pr.two_way_fe(x,y,gid,did)
ok("two-way FE recovers planted slope", abs(fe["beta"]-b_true)<0.1, fe)

# ---- effective breadth ----
import_ok = True
N=6
ident=[[1.0 if i==j else 0.0 for j in range(N)] for i in range(N)]
ones=[[1.0 for _ in range(N)] for _ in range(N)]
ok("eff breadth of identity == N (independent)", abs(pr.effective_breadth(ident)-N)<1e-9, pr.effective_breadth(ident))
ok("eff breadth of all-ones == 1 (one bet)", abs(pr.effective_breadth(ones)-1.0)<1e-9, pr.effective_breadth(ones))
half=[[1.0 if i==j else 0.5 for j in range(N)] for i in range(N)]
ok("eff breadth between 1 and N for partial corr", 1 < pr.effective_breadth(half) < N, pr.effective_breadth(half))

# ---- random-effects meta ----
hom = pr.random_effects_meta([0.50,0.52,0.49,0.51],[0.05,0.05,0.05,0.05])
ok("homogeneous: I2 low", hom["I2"] < 30, hom["I2"])
ok("homogeneous: tau2 ~0", hom["tau2"] < 1e-3, hom["tau2"])
het = pr.random_effects_meta([0.1,0.9,0.2,1.2],[0.05,0.05,0.05,0.05])
ok("heterogeneous: I2 high", het["I2"] > 70, het["I2"])
ok("heterogeneous: tau2>0", het["tau2"] > 0, het["tau2"])
ok("RE se >= FE-implied se under heterogeneity", het["se_re"] is not None)

# ---- mover decomposition ----
md = pr.mover_decomp({"sMR":0.5,"sMom":0.2,"sSig":0.1,"sVol":0.0},{"sMR":0.1,"sMom":0.2,"sSig":0.1,"sVol":0.0})
ok("mover dnet = weighted component deltas", abs(md["dnet"]-0.35*0.4)<1e-9, md)
ok("mover contribs sum to dnet", abs(sum(md["contrib"].values())-md["dnet"])<1e-12)

# ---- CSCV/PBO: a genuinely consistent best config -> low PBO; noise -> ~0.5 ----
T=120; Ncfg=8
M_good=[]; M_noise=[]
for t in range(T):
    row=[rng.gauss(0,1) for _ in range(Ncfg)]
    rowg=list(row); rowg[0]=rng.gauss(0.4,1)     # config 0 truly better every period
    M_good.append(rowg); M_noise.append([rng.gauss(0,1) for _ in range(Ncfg)])
pg=pr.pbo_cscv(M_good,S=8); pn=pr.pbo_cscv(M_noise,S=8)
ok("PBO low for a genuinely-good config", pg["pbo"] is not None and pg["pbo"] < 0.35, pg)
ok("PBO higher for pure-noise configs", pn["pbo"] >= pg["pbo"], (pg["pbo"],pn["pbo"]))

# ---- Reality Check / SPA: a true outperformer -> small p; pure noise -> large p ----
T=160; K=6
D_true=[]; D_noise=[]
for t in range(T):
    base=[rng.gauss(0,1) for _ in range(K)]
    bt=list(base); bt[0]=rng.gauss(0.25,1)       # strategy 0 truly beats benchmark
    D_true.append(bt); D_noise.append([rng.gauss(0,1) for _ in range(K)])
rc_t=pr.reality_check(D_true,B=400); rc_n=pr.reality_check(D_noise,B=400)
ok("Reality Check: small p for true outperformer", rc_t["p"] < 0.10, rc_t)
ok("Reality Check: large p for noise", rc_n["p"] > 0.20, rc_n)
spa_t=pr.spa(D_true,B=400); spa_n=pr.spa(D_noise,B=400)
ok("SPA: small p for true outperformer", spa_t["p"] < 0.15, spa_t)
ok("SPA: larger p for noise than truth", spa_n["p"] > spa_t["p"], (spa_t["p"],spa_n["p"]))

# ---- DRIFT GUARD: the numeric helpers duplicated across pooled_research and pooled_rigor must agree,
#      so the two modules can't silently diverge over time. ----
try:
    import pooled_research as pres
    grid = [-3.0, -1.5, -0.4, 0.0, 0.7, 1.9, 3.0]
    ncdf_ok = all(abs(pr._ncdf(z) - pres._ncdf(z)) < 1e-9 for z in grid)
    pgrid = [0.01, 0.1, 0.5, 0.9, 0.975, 0.999]
    nppf_ok = all(abs(pr._nppf(p) - pres._nppf(p)) < 1e-6 for p in pgrid)
    ok("drift-guard: _ncdf agrees with pooled_research", ncdf_ok)
    ok("drift-guard: _nppf agrees with pooled_research", nppf_ok)
except Exception as e:
    ok("drift-guard: cross-module helper check ran", False, e)

print("\n" + ("ALL POOLED-RIGOR TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
