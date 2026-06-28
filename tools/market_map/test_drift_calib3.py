import math, random
import drift_calib3 as D
F=[]
def chk(n,c):
    print(("  PASS  " if c else "  FAIL  ")+n)
    if not c: F.append(n)
random.seed(19)

# 1. efficiency ratio: straight trend -> ~1 ; perfectly choppy -> low
up=[100+i for i in range(40)]
chk("ER trending ~1", D.efficiency_ratio(up,39,20)>0.95)
chop=[100+(i%2) for i in range(40)]
chk("ER choppy ~0", D.efficiency_ratio(chop,39,20)<0.2)

# 2. ridge recovers planted coefficients (5-term incl interactions)
X=[];y=[]
for _ in range(3000):
    g=random.gauss(0,0.05); m=random.gauss(0,0.07); R=1.0 if random.random()<0.5 else 0.0
    X.append([1.0,g,m,g*R,m*R]); y.append(0.003+0.4*g-0.1*m+(-0.3)*(g*R)+0.25*(m*R)+random.gauss(0,0.01))
b=D.ridge_fit(X,y,lam=0.05)
chk("recover alpha~0.003", abs(b[0]-0.003)<0.003)
chk("recover bRev~0.4", 0.30<b[1]<0.50)
chk("recover gRev~-0.3 (reversion weaker in trend)", -0.42<b[3]<-0.12)
chk("recover gMom~+0.25 (momentum stronger in trend)", 0.15<b[4]<0.30)

# 3. Driscoll-Kraay inflates SE under cross-sectional dependence (common shock each date)
Xd=[];yd=[];td=[]
for t in range(150):
    Ft=random.gauss(0,1.0)                           # common factor at date t
    for u in range(15):                              # 15 names per date
        g=random.gauss(0,0.05)
        Xd.append([1.0,g]); yd.append(0.2*g + 0.8*g*Ft + random.gauss(0,0.002)); td.append(t)
bd=D.ridge_fit(Xd,yd,lam=0.0)
dk=D.driscoll_kraay_t(Xd,yd,bd,td,8)
# naive iid t on the slope: beta/sqrt(sigma^2 * (X'X)^-1_jj)
n=len(Xd);e=[yd[i]-D.predict(bd,Xd[i]) for i in range(n)];s2=sum(v*v for v in e)/(n-2)
XtX=[[0,0],[0,0]]
for xi in Xd:
    for a in range(2):
        for c in range(2): XtX[a][c]+=xi[a]*xi[c]
inv=D._inv(XtX); se_iid=math.sqrt(s2*inv[1][1]); t_iid=bd[1]/se_iid
chk("DK |t| < iid |t| under cross-sectional dependence", abs(dk[1])<abs(t_iid))
chk("DK still finds slope (|t|>2)", abs(dk[1])>2)

# 4. CRPS closed form + limit
chk("CRPS(N(0,1),0)=0.2337", abs(D.crps_gaussian(0,1,0)-0.233692)<1e-4)
chk("CRPS->|y-mu| as sigma->0", abs(D.crps_gaussian(0,1e-9,2)-2)<1e-3)
# 5. PIT + KS
chk("PIT at y=mu = 0.5", abs(D.pit_gaussian(1.0,0.5,1.0)-0.5)<1e-9)
us=[(i+0.5)/200 for i in range(200)]
chk("KS of uniform sample ~0", D.ks_uniform(us)<0.02)

# 6. regime separation end-to-end: build series with regime-dependent dynamics
def mkseries():
    c=[100.0]
    for k in range(700):
        t=len(c)-1; er=D.efficiency_ratio(c,t,20) if t>=20 else 0.0; R=er>0.5
        fair=100.0
        if R: step=0.03*(math.log(c[-1])-math.log(c[max(0,t-21)]))      # trend: momentum
        else: step=0.05*(math.log(fair)-math.log(c[-1]))                # range: reversion
        c.append(max(1.0,c[-1]*math.exp(step+random.gauss(0,0.012))))
    return c
series=[mkseries() for _ in range(10)]
res=D.calibrate3(series,H=20,win=20,mwin=21,lam=4.0)
chk("calibrate3 returns regime + DK + CRPS/PIT keys",
    set(["revRange","revTrend","momRange","momTrend","dkT","oosR2","crps","pitKS","gated"])<=set(res.keys()))
chk("gating is a bool", isinstance(res["gated"],bool))
chk("if not gated, DK t-stats present", res["gated"] or ("rev" in res["dkT"]))

# 7. random walk -> gated (betas zeroed)
rw=[]
for _ in range(10):
    c=[100.0]
    for _ in range(700): c.append(max(1.0,c[-1]*math.exp(random.gauss(0,0.012))))
    rw.append(c)
rr=D.calibrate3(rw,H=20,win=20,mwin=21,lam=4.0)
chk("random walk GATED (betas zero)", rr["gated"] and rr["betaRev"]==0.0 and rr["betaMom"]==0.0 and rr["gRev"]==0.0)
print("\n"+("ALL DRIFT-CALIB3 TESTS PASSED" if not F else "FAILED: %s"%F)); import sys; sys.exit(1 if F else 0)
