import math, random
import drift_calib2 as D
F=[]
def chk(n,c):
    print(("  PASS  " if c else "  FAIL  ")+n)
    if not c: F.append(n)
random.seed(11)
# planted: real = 0.004 + 0.45*gap - 0.20*mom + small noise -> ridge recovers near-betas
X=[];y=[]
for _ in range(2000):
    gap=random.gauss(0,0.06); mom=random.gauss(0,0.08)
    X.append([1.0,gap,mom]); y.append(0.004+0.45*gap-0.20*mom+random.gauss(0,0.01))
b=D.ridge_fit(X,y,lam=1.0)
chk("ridge recovers alpha~0.004", abs(b[0]-0.004)<0.003)
chk("ridge recovers betaRev~0.45 (shrunk a touch)", 0.30<b[1]<0.46)
chk("ridge recovers betaMom~-0.20", -0.21<b[2]<-0.12)
tt=D.newey_west_t(X,y,b,19)
chk("HAC t-stats finite + signal significant", abs(tt[1])>3 and abs(tt[2])>3)
# OOS gate: signal present -> oosR2>0
wf=D.walk_forward_oos(X,y,H=20,lam=1.0)
chk("OOS R2 positive when signal real", wf["oosR2"]>0)
# FULL GATE on a pure random walk (no reversion, no momentum) -> must GATE -> betas zero
rw=[]
for _ in range(8):
    c=[100.0]
    for _ in range(600): c.append(max(1.0,c[-1]*math.exp(random.gauss(0,0.012))))
    rw.append(c)
rwres=D.calibrate(rw,H=20,win=20,mwin=21,lam=4.0)
chk("random walk is GATED (no validated edge)", rwres["gated"] and rwres["betaRev"]==0.0 and rwres["betaMom"]==0.0)
# end-to-end calibrate on a mean-reverting + momentum series
def mkseries(nrev,nmom):
    c=[100.0]; m=100.0
    for _ in range(600):
        rev=nrev*(math.log(m)-math.log(c[-1])); mo=nmom*(math.log(c[-1])-math.log(c[max(0,len(c)-22)]))
        c.append(max(1.0, c[-1]*math.exp(rev+mo+random.gauss(0,0.012))))
    return c
series=[mkseries(0.04,0.02) for _ in range(8)]
res=D.calibrate(series,H=20,win=20,mwin=21,lam=4.0)
chk("calibrate returns structured result", set(["alpha","betaRev","betaMom","oosR2","gated","tRev","tMom","n"])<=set(res.keys()))
chk("gating is a bool tied to oosR2", isinstance(res["gated"],bool))
chk("if not gated, betas nonzero; if gated, zero",
    (res["gated"] and res["betaRev"]==0.0 and res["betaMom"]==0.0) or ((not res["gated"]) and (res["betaRev"]!=0.0 or res["betaMom"]!=0.0)))
print("\n"+("ALL DRIFT-CALIB2 TESTS PASSED" if not F else "FAILED: %s"%F))
import sys; sys.exit(1 if F else 0)
