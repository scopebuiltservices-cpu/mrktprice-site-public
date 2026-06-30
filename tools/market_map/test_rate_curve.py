#!/usr/bin/env python3
"""Offline tests for rate_curve: the load-bearing par-yield -> zero/discount bootstrap math.

Covers the public API directly (ZeroCurve(pillars), bootstrap_zero(pts), Curve(par_pts),
default_curve(), .df(T), .rate_for(T), .par_rate_approx(T)):
  - discount factors are monotone non-increasing in maturity (normal upward curve)
  - the bootstrapped zero rate differs from the naive log(1+par) approximation (bootstrap is real)
  - round-trip: -ln(df(T))/T == rate_for(T)
  - negative-rate handling: a negative pillar doesn't crash and gives df>1
  - inverted curve (short rate > long rate) interpolates sensibly (monotone down in rate)
  - steep curve + missing-tenor interpolation lands strictly between neighbours
  - par_rate_approx diagnostic returns a number distinct from the zero rate
Run: python3 test_rate_curve.py"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate_curve as rc

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# ---------------------------------------------------------------- 1) DFs monotone non-increasing
c = rc.default_curve()
Ts = [0.1, 0.25, 0.5, 1, 2, 3, 5, 7, 10]
dfs = [c.df(T) for T in Ts]
mono = all(dfs[i] >= dfs[i + 1] - 1e-12 for i in range(len(dfs) - 1))
ok("discount factors monotone non-increasing in T (upward curve)", mono, dfs)
ok("all DFs in (0, 1] for a positive-rate curve", all(0 < d <= 1.0 + 1e-12 for d in dfs), dfs)

# ---------------------------------------------------------------- 2) zero rate != naive log(1+par)
# On the coupon region the bootstrapped zero must differ from the front-end log(1+par_yield) approx.
diffs = [abs(c.rate_for(T) - c.par_rate_approx(T)) for T in (2, 3, 5, 7, 10)]
ok("bootstrapped zero differs from naive log(1+par) approx (>1bp somewhere)",
   max(diffs) > 1e-4, [round(x, 6) for x in diffs])

# ---------------------------------------------------------------- 3) round-trip rate_for <-> df
rt = []
for T in Ts:
    z = c.rate_for(T)
    z_from_df = -math.log(c.df(T)) / T
    rt.append(abs(z - z_from_df))
ok("round-trip: -ln(df(T))/T == rate_for(T)", max(rt) < 1e-9, [round(x, 12) for x in rt])

# ---------------------------------------------------------------- 4) negative-rate handling
neg = rc.ZeroCurve([(0.5, -0.005), (1.0, -0.002), (2.0, 0.001), (5.0, 0.01)])
try:
    df_neg = neg.df(0.5)            # negative zero rate -> df > 1
    z_neg = neg.rate_for(0.5)
    crashed = False
except Exception as e:
    df_neg = None; z_neg = None; crashed = True
ok("negative pillar does not crash", not crashed)
ok("df > 1 for a negative zero rate", (df_neg is not None and df_neg > 1.0), df_neg)
ok("rate_for recovers the negative rate", (z_neg is not None and z_neg < 0), z_neg)

# ---------------------------------------------------------------- 5) inverted curve interpolates sensibly
inv = rc.ZeroCurve([(0.25, 0.055), (1.0, 0.050), (5.0, 0.040), (10.0, 0.035)])  # short > long
zs = [inv.rate_for(T) for T in (0.25, 1.0, 5.0, 10.0)]
ok("inverted curve: zero rates monotone decreasing with T", all(zs[i] >= zs[i + 1] - 1e-12 for i in range(len(zs) - 1)), zs)
mid = inv.rate_for(2.5)            # between the 1y (0.050) and 5y (0.040) pillars
ok("inverted curve: interpolated 2.5y rate strictly between neighbours", 0.040 < mid < 0.050, mid)

# ---------------------------------------------------------------- 6) steep curve + missing-tenor interpolation
steep = rc.ZeroCurve([(1.0, 0.010), (10.0, 0.060)])   # very steep, 4y pillar absent
z4 = steep.rate_for(4.0)
ok("steep curve: missing-tenor 4y interpolates strictly between 1y and 10y", 0.010 < z4 < 0.060, z4)
df4 = steep.df(4.0)
ok("steep curve: 4y DF strictly between its neighbours' DFs", steep.df(10.0) < df4 < steep.df(1.0), (steep.df(1.0), df4, steep.df(10.0)))

# ---------------------------------------------------------------- 7) par_rate_approx diagnostic distinct & numeric
pa = c.par_rate_approx(5.0)
ok("par_rate_approx returns a finite number", isinstance(pa, float) and pa == pa and abs(pa) != float("inf"), pa)
ok("par_rate_approx diagnostic distinct from zero rate at 5y", abs(pa - c.rate_for(5.0)) > 1e-9, (pa, c.rate_for(5.0)))

# ---------------------------------------------------------------- 8) bootstrap_zero produces real zero pillars
zp = rc.bootstrap_zero(rc._FALLBACK)
ok("bootstrap_zero returns sorted (T, zero) pillars", zp == sorted(zp) and all(len(p) == 2 for p in zp), zp[:3])
# the bootstrapped 10y zero must differ from the raw par log(1+y) on a sloped curve
par10 = math.log(1.0 + dict(rc._FALLBACK)[10])
z10 = rc.ZeroCurve(zp).rate_for(10.0)
ok("bootstrapped 10y zero != log(1+par_10y)", abs(z10 - par10) > 1e-5, (z10, par10))

print("\n" + ("ALL RATE-CURVE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
