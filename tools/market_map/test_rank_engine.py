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

# empirical-Bayes: tau^2 recovers signal var net of noise; posterior shrinks noisier names more; sd<se
import random as _rnd
_rnd.seed(11)
_vals = []; _ses = []
for _ in range(4000):
    _sig = _rnd.gauss(0, math.sqrt(4.0)); _vals.append(_sig + _rnd.gauss(0, 1.5)); _ses.append(1.5)
ok("eb_tau2 recovers signal var net of noise", abs(R.eb_tau2(_vals, _ses) - 4.0) < 0.5)
ok("eb_tau2 ~0 when pure noise", R.eb_tau2([_rnd.gauss(0, 1.5) for _ in range(4000)], [1.5] * 4000) < 0.4)
_pc = R.eb_posterior(10.0, 0.5, 2.0, 4.0); _pn = R.eb_posterior(10.0, 4.0, 2.0, 4.0)
ok("eb posterior: noisier shrinks toward center more", abs(_pn["mu"] - 2.0) < abs(_pc["mu"] - 2.0))
ok("eb posterior sd identity sd^2==w*se^2", close(_pc["sd"] ** 2, _pc["w"] * 0.5 * 0.5))
ok("eb posterior w in (0,1)", 0 < _pc["w"] < 1 and 0 < _pn["w"] < 1)
ok("eb tiny se -> w~1 (no shrink)", R.eb_posterior(10.0, 1e-6, 2.0, 4.0)["w"] > 0.999)

# "Omitted Strategies" extensions
ok("effective_breadth rho=0 -> n", close(R.effective_breadth(150, 0.0), 150))
ok("effective_breadth rho>0 -> <n,>1", 1 < R.effective_breadth(150, 0.3) < 150)
ok("effective_breadth lowers the multiplicity bar", math.sqrt(2 * math.log(R.effective_breadth(150, 0.4))) < math.sqrt(2 * math.log(150)))
ok("enb_entropy equal weights = k", close(R.enb_entropy([1, 1, 1, 1]), 4))
ok("enb_entropy concentrated -> ~1", R.enb_entropy([100, 1, 1, 1]) < 1.6)
ok("trading_cost positive", R.trading_cost(3.0) > 0)
ok("net_alpha shrinks toward 0 both sides", R.net_alpha(6.0, 1.0) == 5.0 and R.net_alpha(-6.0, 1.0) == -5.0)
import random as _r2
_r2.seed(2)
_rr = [_r2.gauss(0, 0.02) for _ in range(400)] + [-0.15, -0.12]
_es = R.cvar_es(_rr, 0.05)
ok("cvar_es positive loss", _es is not None and _es > 0)
ok("tail_adjust haircuts the edge", R.tail_adjust(5.0, _es, 0.5) < 5.0)
ok("decay_alpha half-life halves", close(R.decay_alpha(8.0, 10, 10), 4.0))
ok("transition_gate hysteresis", R.transition_gate(5.0, 5.05, 0.1) == 5.0 and R.transition_gate(5.0, 5.5, 0.1) == 5.5)
_r2.seed(7)
_X = []
for _ in range(18):
    _fz = _r2.gauss(0, 1)
    _X.append([0.55 * _fz + 0.83 * _r2.gauss(0, 1) for _ in range(12)])
_d, _Sig = R.ledoit_wolf(_X)
ok("ledoit_wolf delta in (0,1)", 0 < _d < 1)
ok("deflated_sharpe deflates for trials (DSR<PSR)", R.deflated_sharpe(0.5, 250, 0, 3, 50) < R.deflated_sharpe(0.5, 250, 0, 3, 1))
ok("deflated_sharpe decreasing in trials", R.deflated_sharpe(0.5, 250, 0, 3, 500) < R.deflated_sharpe(0.5, 250, 0, 3, 5))

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
    _eb = R.eb_posterior(row["tot"], row["se"], g["ebCenter"], g["ebTau2"])
    if not (close(_eb["mu"], row["ebMu"]) and close(_eb["sd"], row["ebSd"]) and close(_eb["w"], row["ebW"])):
        allok = False
    if not (close(R.net_alpha(row["tot"], 1.0), row["netAlpha"]) and close(R.decay_alpha(row["tot"], 5, 21), row["decayMu"])
            and close(R.tail_adjust(row["tot"], 0.8, 0.1), row["tailAdj"])):
        allok = False
if not close(R.eb_tau2([r["tot"] for r in g["rows"]], [r["se"] for r in g["rows"]]), g["ebTau2"]):
    allok = False
if not (close(R.effective_breadth(g["n_tests"], 0.3), g["effBreadth"]) and close(R.enb_entropy([4.0, 2.0, 1.0, 1.0, 0.5]), g["enb"])
        and close(R.trading_cost(3.0), g["tradingCost"]) and close(R.deflated_sharpe(0.5, 250, 0.0, 3.0, g["n_tests"]), g["dsr"])):
    allok = False
ok("golden fixture reproduced", allok)

print("\n" + ("ALL RANK-ENGINE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
