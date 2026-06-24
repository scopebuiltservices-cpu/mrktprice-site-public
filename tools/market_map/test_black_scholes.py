"""Proves the BS engine against published references. Run: python3 test_black_scholes.py"""
import math, black_scholes as bs

def approx(a, b, tol=1e-4): assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"
fails = 0
def check(name, fn):
    global fails
    try: fn(); print(f"  PASS  {name}")
    except AssertionError as e:
        fails += 1; print(f"  FAIL  {name}: {e}")

# 1) Hull, Options Futures & Other Derivatives — S=42,K=40,r=.10,sigma=.20,T=.5
#    Textbook answers: call = 4.76, put = 0.81
check("Hull call=4.76", lambda: approx(bs.bs_price(42,40,0.5,0.10,0.20,0,"C"), 4.7594, 1e-3))
check("Hull put=0.81",  lambda: approx(bs.bs_price(42,40,0.5,0.10,0.20,0,"P"), 0.8086, 1e-3))

# 2) Put-call parity: C - P = S e^{-qT} - K e^{-rT}
def parity():
    S,K,T,r,sig,q = 100,95,0.75,0.03,0.28,0.015
    c = bs.bs_price(S,K,T,r,sig,q,"C"); p = bs.bs_price(S,K,T,r,sig,q,"P")
    approx(c - p, S*math.exp(-q*T) - K*math.exp(-r*T), 1e-9)
check("put-call parity", parity)

# 3) exact normal CDF anchors
check("N(0)=0.5", lambda: approx(bs.norm_cdf(0), 0.5, 1e-12))
check("N(1.96)=0.975", lambda: approx(bs.norm_cdf(1.959964), 0.975, 1e-5))

# 4) greeks: known signs/bounds + gamma=vega/(S^2 sigma T) identity
def greek_props():
    S,K,T,r,sig,q = 100,100,1.0,0.05,0.2,0.0
    gC = bs.greeks(S,K,T,r,sig,q,"C"); gP = bs.greeks(S,K,T,r,sig,q,"P")
    assert 0 < gC["delta"] < 1 and -1 < gP["delta"] < 0
    assert gC["gamma"] > 0 and gC["vega"] > 0
    approx(gC["delta"] - gP["delta"], math.exp(-q*T), 1e-9)   # delta parity
    # vega and gamma relationship: vega = gamma * S^2 * sigma * T
    approx(gC["vega"], gC["gamma"] * S*S * sig * T, 1e-6)
check("greek properties", greek_props)

# 5) ATM call delta ≈ e^{-qT} N(d1) ~ a bit above 0.5
check("ATM call delta", lambda: approx(bs.greeks(100,100,1,0.05,0.2,0,"C")["delta"], 0.6368, 1e-3))

# 6) Implied-vol round trip across the surface (recover sigma to 1e-6)
def iv_roundtrip():
    for S in (50,100,250):
        for K in (0.8*S,S,1.2*S):
            for T in (0.08,0.5,2.0):
                for sig in (0.12,0.35,0.80):
                    for kind in ("C","P"):
                        px = bs.bs_price(S,K,T,0.04,sig,0.01,kind)
                        if px < 1e-6: continue
                        got = bs.implied_vol(px,S,K,T,0.04,0.01,kind)
                        assert got is not None
                        # price must always be recovered to tolerance
                        approx(bs.bs_price(S,K,T,0.04,got,0.01,kind), px, 1e-4)
                        # sigma is only identifiable where vega is non-trivial
                        if bs.greeks(S,K,T,0.04,sig,0.01,kind)["vega"] > 0.5:
                            assert abs(got-sig) < 1e-4, f"{S,K,T,sig,kind}->{got}"
check("IV round-trip (surface)", iv_roundtrip)

# 7) edge cases don't crash and respect bounds
def edges():
    assert bs.bs_price(100,100,0,0.05,0.2,0,"C") == max(100-100,0)
    assert bs.bs_price(100,80,1,0.05,0.0,0,"C") > 0     # sigma=0 -> intrinsic-ish
    assert bs.implied_vol(150,100,90,1,0.04,0,"C") is None   # price above cap -> no IV
check("edge cases", edges)

# 8) value_chain ties option to same-ticker spot + flags richness
def chain():
    spot=100.0
    fair = bs.bs_price(spot,100,30/365,0.04,0.30,0,"C")
    ch = [{"strike":100,"type":"C","oi":500,"mark":round(fair*1.10,2)},  # 10% rich
          {"strike":105,"type":"P","oi":300,"mark":round(bs.bs_price(spot,105,30/365,0.04,0.30,0,"P"),2)}]
    r = bs.value_chain(ch, spot, 30, r=0.04, ref_vol=0.30)
    assert r and r["summary"]["n"]==2
    c0 = r["contracts"][0]
    assert c0["bsValue"]>0 and c0["richnessPct"]>5   # detected richness
    assert r["summary"]["atmIVpct"] is not None
check("value_chain richness", chain)

print(f"\n{'ALL TESTS PASS' if fails==0 else str(fails)+' TEST(S) FAILED'}")
raise SystemExit(1 if fails else 0)
