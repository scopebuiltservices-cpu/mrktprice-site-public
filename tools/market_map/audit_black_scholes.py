#!/usr/bin/env python3
"""Independent audit: prove the analytic Black-Scholes-Merton is correct by cross-checking
against (1) finite-difference greeks and (2) Monte-Carlo risk-neutral pricing — no reuse of
the same closed forms — plus (3) application checks inside value_chain.

Run:
    python3 audit_black_scholes.py            # full (1,000,000-path MC)
    python3 audit_black_scholes.py --quick    # fast MC for CI
    python3 audit_black_scholes.py --json      # machine-readable result

Exit 0 = all checks pass, 1 = at least one failed (CI ::error:: annotations are printed).
"""
from __future__ import annotations
import argparse, math, random, sys
import black_scholes as bs


def _make_ok(fails, results):
    def ok(name, cond, detail=""):
        results.append({"name": name, "pass": bool(cond), "detail": detail})
        print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  -> " + detail))
        if not cond:
            fails.append(name)
            print("::error title=BSM audit::%s -> %s" % (name, detail))
    return ok


def fd_greeks(S, K, T, r, sig, q, kind):
    P = lambda S=S, T=T, r=r, sig=sig: bs.bs_price(S, K, T, r, sig, q, kind)
    hS = 1e-4 * S; hv = 1e-5; hT = 1e-5; hr = 1e-6
    delta = (P(S=S + hS) - P(S=S - hS)) / (2 * hS)
    gamma = (P(S=S + hS) - 2 * P() + P(S=S - hS)) / (hS * hS)
    vega = (P(sig=sig + hv) - P(sig=sig - hv)) / (2 * hv)
    theta = -(P(T=T + hT) - P(T=T - hT)) / (2 * hT)   # dV/dt = -dV/dT
    rho = (P(r=r + hr) - P(r=r - hr)) / (2 * hr)
    return delta, gamma, vega, theta, rho


def mc_price(S, K, T, r, sig, q, kind, n=1_000_000):
    drift = (r - q - 0.5 * sig * sig) * T; vol = sig * math.sqrt(T); disc = math.exp(-r * T); s = 0.0
    for _ in range(n // 2):                       # antithetic variates
        z = random.gauss(0, 1)
        for zz in (z, -z):
            ST = S * math.exp(drift + vol * zz)
            s += (max(ST - K, 0) if kind == "C" else max(K - ST, 0))
    return disc * (s / n)


def run_audit(mc_n=1_000_000):
    random.seed(20240607)
    fails = []; results = []
    ok = _make_ok(fails, results)

    # (1) finite-difference greeks vs analytic, across a grid
    maxrel = 0.0
    for S in (40, 100, 250):
        for K in (0.85 * S, S, 1.15 * S):
            for T in (0.1, 0.75, 2.0):
                for sig in (0.15, 0.40):
                    for q in (0.0, 0.02):
                        for kind in ("C", "P"):
                            r = 0.04
                            a = bs.greeks(S, K, T, r, sig, q, kind)
                            fd = fd_greeks(S, K, T, r, sig, q, kind)
                            for av, fv in zip((a["delta"], a["gamma"], a["vega"], a["theta"], a["rho"]), fd):
                                rel = abs(av - fv) / max(abs(fv), 1e-6)
                                maxrel = max(maxrel, rel if abs(fv) > 1e-4 else 0)
    ok("analytic greeks == finite-difference (all strikes/T/vol/q, calls&puts)", maxrel < 2e-3,
       "max rel err %.2e" % maxrel)

    # (2) Monte-Carlo risk-neutral price vs analytic
    worst = 0.0; tol = 0.006 if mc_n >= 1_000_000 else 0.02
    for (S, K, T, r, sig, q, kind) in [(100, 100, 1, 0.04, 0.2, 0.0, "C"), (100, 110, 0.5, 0.05, 0.3, 0.02, "P"),
                                       (50, 45, 2, 0.03, 0.25, 0.0, "C"), (250, 260, 0.25, 0.045, 0.5, 0.01, "P")]:
        a = bs.bs_price(S, K, T, r, sig, q, kind); m = mc_price(S, K, T, r, sig, q, kind, n=mc_n)
        rel = abs(a - m) / max(a, 1e-6); worst = max(worst, rel)
        print("     MC check %s S=%s K=%s: analytic=%.4f mc=%.4f rel=%.4f" % (kind, S, K, a, m, rel))
    ok("analytic price == Monte-Carlo risk-neutral price (tol %.1f%%)" % (tol * 100), worst < tol,
       "worst rel %.4f" % worst)

    # (3) application checks in value_chain
    spot = 200.0; T = 45 / 365
    ch = [{"strike": 200, "type": "C", "oi": 1000, "mark": round(bs.bs_price(spot, 200, T, 0.04, 0.34, 0, "C"), 2)}]
    v_self = bs.value_chain(ch, spot, 45, r=0.04)
    v_ref = bs.value_chain(ch, spot, 45, r=0.04, ref_vol=0.28)
    ok("richness uses independent ref vol (RV) -> flags rich", v_ref["contracts"][0]["richnessPct"] > 5,
       str(v_ref["contracts"][0]["richnessPct"]))
    ok("IV premium reported vs ref (34-28=6pts)", abs(v_ref["contracts"][0]["ivPremPts"] - 6.0) < 0.6,
       str(v_ref["contracts"][0]["ivPremPts"]))
    ok("greeks at contract IV (ATM call delta ~0.5-0.6)", 0.5 < v_ref["contracts"][0]["delta"] < 0.62,
       str(v_ref["contracts"][0]["delta"]))
    ok("vega per 1% (0<vega<1) & gamma>0", 0 < v_ref["contracts"][0]["vega"] < 1 and v_ref["contracts"][0]["gamma"] > 0)
    em = v_self["summary"]["expMovePct"]; expect = 0.34 * math.sqrt(T) * 100
    ok("expected move = ATM IV*sqrt(T)", abs(em - expect) < 0.05, "%s vs %.2f" % (em, expect))
    c = bs.bs_price(spot, 200, T, 0.04, 0.3, 0.01, "C"); p = bs.bs_price(spot, 200, T, 0.04, 0.3, 0.01, "P")
    ok("parity with q inside pricer",
       abs((c - p) - (spot * math.exp(-0.01 * T) - 200 * math.exp(-0.04 * T))) < 1e-9)
    return fails, results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Independent BSM correctness audit.")
    ap.add_argument("--quick", action="store_true", help="fast MC (100k paths) for CI")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON result")
    a = ap.parse_args(argv)
    fails, results = run_audit(mc_n=100_000 if a.quick else 1_000_000)
    if a.json:
        import json
        print(json.dumps({"passed": not fails, "fails": fails, "checks": results}, indent=2))
    else:
        print("\n" + ("AUDIT PASSED — BSM correctly applied" if not fails
                      else "%d CHECK(S) FAILED: %s" % (len(fails), fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
