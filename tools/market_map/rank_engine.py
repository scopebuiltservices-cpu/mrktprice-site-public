#!/usr/bin/env python3
"""
rank_engine.py — the mastery ranking mathematics for the Bull/Bear board (pure-stdlib reference).

The old board ranks by the optimistic POINT estimate `tot` (expected 1-month total return). That over-ranks
noisy, low-conviction names. This engine ranks by a CONFIDENCE-ADJUSTED, MULTIPLICITY-DEFLATED, calibrated
score instead. Verified-engine pattern: this is authoritative; rank_engine.js is locked to tools/rank_golden.json.

Pieces (each defensible, each unit-tested):
  grinold_kahn(ic, sigma, z)      Grinold-Kahn forecast alpha = IC * sigma * z (turn a score into a
                                  CALIBRATED expected excess return using realized factor skill IC).
  conviction_sigma(base, z)       effective forecast sigma that SHRINKS with conviction: low |z| -> larger
                                  sigma -> larger uncertainty penalty.
  lcb_score(mu, sigma, k)         lower-confidence-bound rank score: move the edge toward 0 by k*sigma, in
                                  the direction of its own sign. Rank by what you can DEFEND, not the peak.
  deflated_conviction(z, n)       selection-bias-aware conviction: the max |z| over n names is inflated
                                  ~sqrt(2 ln n); report the conviction IN EXCESS of that multiplicity bar.
  stein_shrink(x, se, tau)        empirical-Bayes / James-Stein shrinkage of a noisy estimate toward 0.
  ewma_score(prev, now, lam)      run-over-run smoothing to damp board whipsaw (rank stability).
  composite_rank_score(...)       the headline score the board ranks by.
"""
import json, math, os

__all__ = ["grinold_kahn", "conviction_sigma", "lcb_score", "deflated_conviction", "stein_shrink",
           "ewma_score", "composite_rank_score"]


def grinold_kahn(ic, sigma, z):
    """Calibrated expected excess return = IC * sigma * z (Grinold-Kahn 'alpha = IC·σ·score')."""
    return ic * sigma * z


def conviction_sigma(base_sigma, z, floor=0.2, full=1.5):
    """Effective forecast sigma that grows as conviction shrinks: sigma = base / clamp(|z|/full, floor, 1).
    At |z|>=full (HIGH) -> base; at |z|->0 -> base/floor (max uncertainty)."""
    rel = abs(z) / full if full > 0 else 0.0
    rel = max(floor, min(1.0, rel))
    return base_sigma / rel if rel > 0 else base_sigma


def lcb_score(mu, sigma, k=0.5):
    """Lower-confidence-bound rank score: shift the edge toward 0 by k*sigma in the direction of its sign,
    so a high-uncertainty name (either side) is penalized toward neutral. Rank bulls desc, bears asc."""
    if sigma is None or sigma != sigma or sigma < 0:
        return mu
    pen = k * sigma
    if mu >= 0:
        return mu - pen
    return mu + pen


def deflated_conviction(z, n_tests):
    """Conviction in EXCESS of the cross-sectional multiplicity bar. With n names the largest |z| is
    inflated ~E[max] = sqrt(2 ln n); return sign(z) * max(0, |z| - sqrt(2 ln n))."""
    if n_tests is None or n_tests < 2:
        return z
    bar = math.sqrt(2.0 * math.log(n_tests))
    excess = max(0.0, abs(z) - bar)
    return math.copysign(excess, z) if z != 0 else 0.0


def stein_shrink(x, se, tau):
    """James-Stein / empirical-Bayes shrinkage toward 0: w = tau^2/(tau^2+se^2); noisier estimates shrink more."""
    if se is None or se <= 0 or tau is None or tau <= 0:
        return x
    w = (tau * tau) / (tau * tau + se * se)
    return w * x


def ewma_score(prev, now, lam=0.5):
    """Run-over-run smoothing for rank stability (damps daily whipsaw). lam in (0,1]; prev None -> now."""
    if prev is None or prev != prev:
        return now
    return lam * now + (1.0 - lam) * prev


def composite_rank_score(tot, z, base_sigma, k=0.5, n_tests=None, prev=None, lam=1.0):
    """Headline ranking score the board sorts by: confidence-adjusted (LCB with conviction-scaled sigma),
    optionally EWMA-smoothed. n_tests is carried for the deflated-conviction display, not the score."""
    sig = conviction_sigma(base_sigma, z)
    s = lcb_score(tot, sig, k)
    return ewma_score(prev, s, lam) if (prev is not None) else s


# ---- committed golden fixture (both languages lock to it) ----
def gen_fixture():
    cases = [
        {"tot": 6.5, "z": 2.1, "base_sigma": 9.0},     # high edge, high conviction
        {"tot": 6.0, "z": 0.5, "base_sigma": 9.0},     # high edge, LOW conviction -> should rank lower than above
        {"tot": -5.0, "z": -1.8, "base_sigma": 9.0},   # bear, high conviction
        {"tot": -4.8, "z": -0.4, "base_sigma": 9.0},   # bear, low conviction
        {"tot": 1.2, "z": 3.0, "base_sigma": 6.0},     # small edge, very high conviction
    ]
    out = []
    for c in cases:
        out.append({
            "tot": c["tot"], "z": c["z"], "base_sigma": c["base_sigma"],
            "convSigma": conviction_sigma(c["base_sigma"], c["z"]),
            "lcb": lcb_score(c["tot"], conviction_sigma(c["base_sigma"], c["z"]), 0.5),
            "score": composite_rank_score(c["tot"], c["z"], c["base_sigma"], 0.5, len(cases)),
            "zAdj": deflated_conviction(c["z"], 150),
            "gk": grinold_kahn(0.08, c["base_sigma"], c["z"]),
        })
    return {"fixture_version": 1, "case": "rank-engine-core", "k": 0.5, "n_tests": 150, "rows": out}


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rank_golden.json")
    json.dump(gen_fixture(), open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p))


if __name__ == "__main__":
    main()
