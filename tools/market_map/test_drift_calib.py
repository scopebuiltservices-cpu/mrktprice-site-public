import math, random
import drift_calib as D
F=[]
def chk(n,c):
    print(("  PASS  " if c else "  FAIL  ")+n)
    if not c: F.append(n)
# recovers a planted slope: real = 0.5*gap (+ tiny noise) -> shrink ~0.5
random.seed(7)
pred=[random.gauss(0,0.05) for _ in range(400)]; real=[0.5*g+random.gauss(0,1e-4) for g in pred]
r=D.optimal_shrink(pred,real,prior=0.6,prior_n=20)
chk("recovers planted shrink ~0.5", abs(r["shrink"]-0.5)<0.05)
# tiny sample -> stays near the 0.6 prior
r2=D.optimal_shrink([0.01,0.02],[0.02,0.01],prior=0.6,prior_n=20)
chk("tiny sample near prior", abs(r2["shrink"]-0.6)<0.05)
# clamps to [0,1]: planted slope 5 -> clamped
big=[0.01*i for i in range(1,200)]; bigy=[5*x for x in big]
chk("clamps high slope to <=1", D.optimal_shrink(big,bigy,prior_n=0)["shrink"]<=1.0)
chk("no negative shrink", D.optimal_shrink(big,[-5*x for x in big],prior_n=0)["shrink"]>=0.0)
# gap_pairs on a mean-reverting series produces pairs whose slope is positive (reversion realizes)
c=[100.0]; m=100.0
for _ in range(300):
    m=100.0; nxt=c[-1]+0.25*(m-c[-1])+random.gauss(0,0.5); c.append(max(1.0,nxt))
gp=D.gap_pairs(c,H=20,win=20)
chk("gap_pairs nonempty on reverting series", len(gp)>50)
uni=D.calibrate_universe([c],H=20,win=20)
chk("universe calib in [0,1] with positive reversion", 0.0<=uni["shrink"]<=1.0 and uni["raw"]>0)
chk("NaN-safe ols", D.ols_slope([float('nan'),1,2],[1,2,4])==2.0)
print("\n"+("ALL DRIFT-CALIB TESTS PASSED" if not F else "FAILED: %s"%F))
import sys; sys.exit(1 if F else 0)
