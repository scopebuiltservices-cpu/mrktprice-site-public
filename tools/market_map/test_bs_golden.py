#!/usr/bin/env python3
"""Golden-fixture audit suite for black_scholes.py.

Implements the test battery prescribed by the "Audit Framework for Black-Scholes and
Black-Scholes-Merton Implementations": language-independent golden fixtures (price + Greeks),
edge/limit cases, put-call parity, IV round-trip, monotonicity, convexity-in-strike, the BSM
PDE residual, and an American-style guardrail. Fixtures live in bs_golden.json so the same
machine-precision numbers are the single source of truth across runtimes.

Run: python3 test_bs_golden.py
"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import black_scholes as bs
try:
    import american as am
    HAVE_AM = True
except Exception:
    HAVE_AM = False

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

HERE = os.path.dirname(os.path.abspath(__file__))
G = json.load(open(os.path.join(HERE, "bs_golden.json")))
TOL = G["tol"]

# 1) Price fixtures (call + put) to machine precision
for c in G["cases"]:
    S, K, T, r, q, sg = c["S"], c["K"], c["T"], c["r"], c["q"], c["sigma"]
    pc = bs.bs_price(S, K, T, r, sg, q, "C"); pp = bs.bs_price(S, K, T, r, sg, q, "P")
    ok("price call %s" % c["name"], abs(pc - c["call"]) <= TOL["price"], abs(pc - c["call"]))
    ok("price put  %s" % c["name"], abs(pp - c["put"]) <= TOL["price"], abs(pp - c["put"]))

# 2) Greek fixtures (delta, gamma, vega)
for c in G["cases"]:
    S, K, T, r, q, sg = c["S"], c["K"], c["T"], c["r"], c["q"], c["sigma"]
    g = bs.greeks(S, K, T, r, sg, q, "C")
    ok("delta %s" % c["name"], abs(g["delta"] - c["callDelta"]) <= TOL["greek"], abs(g["delta"] - c["callDelta"]))
    ok("gamma %s" % c["name"], abs(g["gamma"] - c["gamma"]) <= TOL["greek"], abs(g["gamma"] - c["gamma"]))
    ok("vega  %s" % c["name"], abs(g["vega"] - c["vega"]) <= TOL["greek"], abs(g["vega"] - c["vega"]))

# 3) Edge / limit fixtures (expiry intrinsic + zero-vol discounted intrinsic)
for e in G["edge"]:
    v = bs.bs_price(e["S"], e["K"], e["T"], e["r"], e["sigma"], e["q"], e["kind"])
    ok("edge %s" % e["name"], abs(v - e["exp"]) <= TOL["price"], (v, e["exp"]))
    ok("edge %s nonneg" % e["name"], v >= -1e-12, v)

# 4) Put-call parity:  C - P = S e^{-qT} - K e^{-rT}
for c in G["cases"]:
    S, K, T, r, q, sg = c["S"], c["K"], c["T"], c["r"], c["q"], c["sigma"]
    lhs = bs.bs_price(S, K, T, r, sg, q, "C") - bs.bs_price(S, K, T, r, sg, q, "P")
    rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
    ok("parity %s" % c["name"], abs(lhs - rhs) <= TOL["parity"] * max(1, S, K), abs(lhs - rhs))

# 5) IV round-trip: price with sigma, invert, reprice
for c in G["cases"]:
    S, K, T, r, q, sg = c["S"], c["K"], c["T"], c["r"], c["q"], c["sigma"]
    for kind in ("C", "P"):
        px = bs.bs_price(S, K, T, r, sg, q, kind)
        iv = bs.implied_vol(px, S, K, T, r, q, kind)
        ok("iv recover %s %s" % (kind, c["name"]), abs(iv - sg) <= TOL["iv"], abs(iv - sg))
        ok("iv reprice %s %s" % (kind, c["name"]), abs(bs.bs_price(S, K, T, r, iv, q, kind) - px) <= 1e-8, None)

# 6) Monotonicity: call increasing in S, decreasing in K; both increasing in sigma
S, K, T, r, q, sg = 100, 100, 1.0, 0.03, 0.01, 0.2
ok("call up in S", bs.bs_price(101, K, T, r, sg, q, "C") > bs.bs_price(99, K, T, r, sg, q, "C"))
ok("call down in K", bs.bs_price(S, 105, T, r, sg, q, "C") < bs.bs_price(S, 95, T, r, sg, q, "C"))
ok("call up in vol", bs.bs_price(S, K, T, r, 0.30, q, "C") > bs.bs_price(S, K, T, r, 0.10, q, "C"))
ok("put  up in vol", bs.bs_price(S, K, T, r, 0.30, q, "P") > bs.bs_price(S, K, T, r, 0.10, q, "P"))

# 7) Convexity in strike: C(K-h) - 2C(K) + C(K+h) >= 0  (butterfly no-arb)
h = 1.0
conv = bs.bs_price(S, K - h, T, r, sg, q, "C") - 2 * bs.bs_price(S, K, T, r, sg, q, "C") + bs.bs_price(S, K + h, T, r, sg, q, "C")
ok("convex in strike (butterfly>=0)", conv >= -1e-10, conv)

# 8) BSM PDE residual:  V_t + (r-q)S V_S + 0.5 s^2 S^2 V_SS - r V = 0, with V_t = -dV/dT.
#    Derivatives taken by central finite-difference straight off the price surface so the test is
#    independent of how greeks() scales/signs theta.
def pde_resid(kind):
    V = bs.bs_price(S, K, T, r, sg, q, kind)
    hS = 1e-3 * S
    Vp = bs.bs_price(S + hS, K, T, r, sg, q, kind); Vm = bs.bs_price(S - hS, K, T, r, sg, q, kind)
    VS = (Vp - Vm) / (2 * hS); VSS = (Vp - 2 * V + Vm) / (hS * hS)
    hT = 1e-4
    VT = (bs.bs_price(S, K, T + hT, r, sg, q, kind) - bs.bs_price(S, K, T - hT, r, sg, q, kind)) / (2 * hT)
    Vt = -VT
    return Vt + (r - q) * S * VS + 0.5 * sg * sg * S * S * VSS - r * V
for kind in ("C", "P"):
    ok("PDE residual %s ~ 0" % kind, abs(pde_resid(kind)) <= 1e-4, abs(pde_resid(kind)))

# 9) American-style guardrail: American put >= European put (early-exercise premium >= 0);
#    American call with q=0 == European call (never early-exercised).
if HAVE_AM:
    euP = bs.bs_price(100, 100, 1.0, 0.06, 0.2, 0.0, "P")
    amP = am.crr_price(100, 100, 1.0, 0.06, 0.2, 0.0, "P", steps=400, american=True)
    ok("American put >= European put", amP >= euP - 1e-9, (amP, euP))
    ok("early-exercise premium > 0 (r>0 put)", amP - euP > 1e-3, amP - euP)
    euC = bs.bs_price(100, 100, 1.0, 0.06, 0.2, 0.0, "C")
    amC = am.crr_price(100, 100, 1.0, 0.06, 0.2, 0.0, "C", steps=400, american=True)
    ok("American call(q=0) ~ European call", abs(amC - euC) <= 5e-2, abs(amC - euC))
else:
    print("  SKIP  american guardrail (american.py not importable)")

print("\n" + ("ALL BS-GOLDEN TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
