#!/usr/bin/env python3
"""Tests for rank_engine.py — the confidence-adjusted ranking math. Planted-structure + golden lock.
Run: python3 test_rank_engine.py"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rank_engine as R

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

def close(a, b, t=1e-9):
    return a == a and b == b and abs(a - b) <= t * (1 + abs(b))

# grinold-kahn
ok("grinold_kahn = ic*sigma*z", close(R.grinold_kahn(0.08, 9.0, 2.0), 0.08 * 9.0 * 2.0))

# alpha_forecast_se: leverage-aware per-name estimation SE (the genuine uncertainty term)
ok("alpha_forecast_se leverage: extreme alpha wider", R.alpha_forecast_se(2.0, 3.0, 0.0, 50.0, 150) > R.alpha_forecast_se(2.0, 0.1, 0.0, 50.0, 150))
ok("alpha_forecast_se scales with resid_sd", R.alpha_forecast_se(4.0, 1.0, 0.0, 50.0, 150) > R.alpha_forecast_se(2.0, 1.0, 0.0, 50.0, 150))
ok("alpha_forecast_se None on bad inputs", R.alpha_forecast_se(0, 1, 0, 50, 150) is None and R.alpha_forecast_se(2, 1, 0, 0, 150) is None)

# conviction_sigma: HIGH conviction -> base; zero conviction -> base/floor
ok("conviction_sigma at |z|>=1.5 == base", close(R.conviction_sigma(9.0, 2.0), 9.0))
ok("conviction_sigma at z=0 == base/0.2", close(R.conviction_sigma(9.0, 0.0), 9.0 / 0.2))
ok("conviction_sigma monotone: low z -> bigger sigma", R.conviction_sigma(9.0, 0.3) > R.conviction_sigma(9.0, 1.2))

# lcb_score: penalize toward 0 by sign
ok("lcb bull mu - k*sigma", close(R.lcb_score(6.0, 4.0, 0.5), 6.0 - 2.0))
ok("lcb bear mu + k*sigma (toward 0)", close(R.lcb_score(-6.0, 4.0, 0.5), -6.0 + 2.0))

# THE headline property — now SE-DRIVEN: a higher-edge but NOISY (high-SE) name must score below a
# slightly-lower-edge but CLEAN (low-SE) name, because the lower-confidence bound haircuts real uncertainty.
hi = R.composite_rank_score(6.0, 2.1, 9.0, 0.5, 150, se=1.0)   # clean estimate
lo = R.composite_rank_score(6.5, 0.5, 9.0, 0.5, 150, se=6.0)   # noisier + weaker conviction
ok("confidence ranking: clean edge beats noisier-bigger edge", hi > lo, (hi, lo))

# deflated conviction: excess over multiplicity bar sqrt(2 ln n)
bar = math.sqrt(2 * math.log(150))
ok("deflated_conviction excess over bar", close(R.deflated_conviction(bar + 1.0, 150), 1.0))
ok("deflated_conviction 0 below bar", R.deflated_conviction(bar - 0.5, 150) == 0.0)
ok("deflated_conviction keeps sign", R.deflated_conviction(-(bar + 1.0), 150) < 0)

# stein shrink + ewma
ok("stein shrinks noisy more", abs(R.stein_shrink(1.0, 2.0, 1.0)) < abs(R.stein_shrink(1.0, 0.5, 1.0)))
ok("stein toward center (borrow strength)", close(R.stein_shrink(10.0, 1.0, 1.0, center=4.0), 4.0 + 0.5 * (10.0 - 4.0)))
ok("ewma prev None -> now", R.ewma_score(None, 5.0) == 5.0)
ok("ewma blends", close(R.ewma_score(2.0, 4.0, 0.5), 3.0))

# golden lock
GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rank_golden.json")
if not os.path.exists(GOLD):
    json.dump(R.gen_fixture(), open(GOLD, "w"), separators=(",", ":"))
g = json.load(open(GOLD))
allok = True
for row in g["rows"]:
    if not (close(R.conviction_sigma(row["base_sigma"], row["z"]), row["convSigma"]) and
            close(R.lcb_score(row["tot"], row["se"], g["k"]), row["lcb"]) and
            close(R.composite_rank_score(row["tot"], row["z"], row["base_sigma"], g["k"], g["n_tests"], se=row["se"]), row["score"]) and
            close(R.alpha_forecast_se(2.0, row["z"], 0.0, 10.0, g["n_tests"]), row["aFse"]) and
            close(R.deflated_conviction(row["z"], 150), row["zAdj"])):
        allok = False
ok("golden fixture reproduced", allok)

print("\n" + ("ALL RANK-ENGINE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
