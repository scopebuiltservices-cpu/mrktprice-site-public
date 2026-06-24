"""Independent audit: prove the analytic BSM is correct by cross-checking against
(1) finite-difference greeks and (2) Monte-Carlo risk-neutral pricing. No reuse of
the same closed forms. Run: python3 audit_black_scholes.py"""
import math, random, black_scholes as bs
random.seed(20240607)
FAILS=[]
def ok(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ")+name+("" if cond else "  -> "+detail))
    if not cond: FAILS.append(name)

# ---- (1) finite-difference greeks vs analytic, across a grid ----
def fd_greeks(S,K,T,r,sig,q,kind):
    P=lambda S=S,T=T,r=r,sig=sig: bs.bs_price(S,K,T,r,sig,q,kind)
    hS=1e-4*S; hv=1e-5; hT=1e-5; hr=1e-6
    delta=(P(S=S+hS)-P(S=S-hS))/(2*hS)
    gamma=(P(S=S+hS)-2*P()+P(S=S-hS))/(hS*hS)
    vega =(P(sig=sig+hv)-P(sig=sig-hv))/(2*hv)
    theta=-(P(T=T+hT)-P(T=T-hT))/(2*hT)          # dV/dt = -dV/dT
    rho  =(P(r=r+hr)-P(r=r-hr))/(2*hr)
    return delta,gamma,vega,theta,rho

maxrel=0.0
for S in (40,100,250):
  for K in (0.85*S,S,1.15*S):
    for T in (0.1,0.75,2.0):
      for sig in (0.15,0.40):
        for q in (0.0,0.02):
          for kind in ("C","P"):
            a=bs.greeks(S,K,T,r:=0.04,sig,q,kind)
            fd=fd_greeks(S,K,T,r,sig,q,kind)
            for nm,av,fv in zip(("delta","gamma","vega","theta","rho"),
                                (a["delta"],a["gamma"],a["vega"],a["theta"],a["rho"]),fd):
              scale=max(abs(fv),1e-6)
              rel=abs(av-fv)/scale
              maxrel=max(maxrel,rel if abs(fv)>1e-4 else 0)
ok("analytic greeks == finite-difference (all strikes/T/vol/q, calls&puts)", maxrel<2e-3, f"max rel err {maxrel:.2e}")

# ---- (2) Monte-Carlo risk-neutral price vs analytic ----
def mc_price(S,K,T,r,sig,q,kind,n=1_000_000):
    drift=(r-q-0.5*sig*sig)*T; vol=sig*math.sqrt(T); disc=math.exp(-r*T); s=0.0
    for _ in range(n//2):                      # antithetic variates
        z=random.gauss(0,1)
        for zz in (z,-z):
            ST=S*math.exp(drift+vol*zz)
            s+= (max(ST-K,0) if kind=="C" else max(K-ST,0))
    mean=s/n; se=disc*1.0  # rough; use payoff variance
    return disc*mean
worst=0.0
for (S,K,T,r,sig,q,kind) in [(100,100,1,0.04,0.2,0.0,"C"),(100,110,0.5,0.05,0.3,0.02,"P"),
                             (50,45,2,0.03,0.25,0.0,"C"),(250,260,0.25,0.045,0.5,0.01,"P")]:
    a=bs.bs_price(S,K,T,r,sig,q,kind); m=mc_price(S,K,T,r,sig,q,kind)
    rel=abs(a-m)/max(a,1e-6); worst=max(worst,rel)
    print(f"     MC check {kind} S={S} K={K}: analytic={a:.4f} mc={m:.4f} rel={rel:.4f}")
ok("analytic price == Monte-Carlo risk-neutral price (<0.6%)", worst<0.006, f"worst rel {worst:.4f}")

# ---- (3) application checks in value_chain ----
spot=200.0; T=45/365
# richness must use an INDEPENDENT ref vol, not each option's own IV:
ch=[{"strike":200,"type":"C","oi":1000,"mark":round(bs.bs_price(spot,200,T,0.04,0.34,0,"C"),2)}]  # mkt IV 34%
v_self=bs.value_chain(ch,spot,45,r=0.04)                       # ref=ATM IV(=34) -> richness ~0 by construction
v_ref =bs.value_chain(ch,spot,45,r=0.04,ref_vol=0.28)          # ref=realized 28% -> option should look RICH
ok("richness uses independent ref vol (RV) -> flags rich", v_ref["contracts"][0]["richnessPct"]>5,
   f'{v_ref["contracts"][0]["richnessPct"]}')
ok("IV premium reported vs ref (34-28=6pts)", abs(v_ref["contracts"][0]["ivPremPts"]-6.0)<0.6,
   f'{v_ref["contracts"][0]["ivPremPts"]}')
# greeks use the contract's own IV (delta at 34% near ATM ~0.55)
ok("greeks at contract IV (ATM call delta ~0.5-0.6)", 0.5<v_ref["contracts"][0]["delta"]<0.62,
   f'{v_ref["contracts"][0]["delta"]}')
# units: vega reported per 1% (small), gamma positive
ok("vega per 1% (0<vega<1) & gamma>0", 0<v_ref["contracts"][0]["vega"]<1 and v_ref["contracts"][0]["gamma"]>0)
# expected move = ATM_IV*sqrt(T)
em=v_self["summary"]["expMovePct"]; expect=0.34*math.sqrt(T)*100
ok("expected move = ATM IV*sqrt(T)", abs(em-expect)<0.05, f"{em} vs {expect:.2f}")
# put-call parity holds inside value_chain pricing
c=bs.bs_price(spot,200,T,0.04,0.3,0.01,"C"); p=bs.bs_price(spot,200,T,0.04,0.3,0.01,"P")
ok("parity with q inside pricer", abs((c-p)-(spot*math.exp(-0.01*T)-200*math.exp(-0.04*T)))<1e-9)

print("\n"+("AUDIT PASSED — BSM correctly applied" if not FAILS else f"{len(FAILS)} CHECK(S) FAILED: {FAILS}"))
raise SystemExit(1 if FAILS else 0)
