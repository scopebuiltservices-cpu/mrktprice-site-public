#!/usr/bin/env python3
"""
rank_engine.py — the mastery ranking mathematics for the Bull/Bear board (pure-stdlib reference).

The old board ranks by the optimistic POINT estimate `tot` (expected 1-month total return). That over-ranks
noisy, low-conviction names. This engine ranks by a CONFIDENCE-ADJUSTED, MULTIPLICITY-DEFLATED, calibrated
score instead. Verified-engine pattern: this is authoritative; rank_engine.js is locked to tools/rank_golden.json.

Pieces (each defensible, each unit-tested):
  grinold_kahn(ic, sigma, z)      Grinold-Kahn forecast alpha = IC * sigma * z (turn a score into a
                                  CALIBRATED expected excess return using realized factor skill IC).
  alpha_forecast_se(...)          PER-NAME standard error of the predicted return from the alpha->return
                                  calibration (mean-response SE, leverage-aware). This is the genuine
                                  uncertainty term the lower-confidence bound should haircut: it is
                                  INDEPENDENT of the point estimate's sign and grows for extreme-alpha names.
  conviction_sigma(base, z)       FALLBACK effective forecast sigma when no per-name SE is available: grows as
                                  conviction shrinks (low |z| -> larger sigma -> larger uncertainty penalty).
  lcb_score(mu, sigma, k)         lower-confidence-bound rank score: move the edge toward 0 by k*sigma, in
                                  the direction of its own sign. Rank by what you can DEFEND, not the peak.
  deflated_conviction(z, n)       selection-bias-aware conviction: the max |z| over n names is inflated
                                  ~sqrt(2 ln n); report the conviction IN EXCESS of that multiplicity bar.
  stein_shrink(x, se, tau, c)     empirical-Bayes / James-Stein shrinkage of a noisy estimate toward a center
                                  c (the cross-sectional mean when borrowing strength; 0 by default).
  ewma_score(prev, now, lam)      run-over-run smoothing to damp board whipsaw (rank stability).
  composite_rank_score(...)       the headline score the board ranks by: LCB with the per-name SE, a soft
                                  multiplicity discount when n_tests is supplied, and optional EWMA.
"""
import json, math, os

__all__ = ["grinold_kahn", "alpha_forecast_se", "conviction_sigma", "lcb_score", "deflated_conviction",
           "stein_shrink", "ewma_score", "composite_rank_score"]


def grinold_kahn(ic, sigma, z):
    """Calibrated expected excess return = IC * sigma * z (Grinold-Kahn 'alpha = IC·σ·score')."""
    return ic * sigma * z


def alpha_forecast_se(resid_sd, alpha, alpha_mean, sxx, n):
    """Standard error of the predicted return from the alpha->return calibration, for ONE name:
        SE = resid_sd * sqrt(1/n + (alpha - alpha_mean)^2 / Sxx)
    This is the mean-response (estimation) uncertainty of the OLS prediction y_hat = a + b*alpha. It is
    heteroskedastic across names through leverage (extreme-alpha names sit far from the design center and
    carry wider bands) and, unlike a return-dispersion proxy, is independent of the point estimate's sign.
    Returns None when inputs are unusable so the caller can fall back to the conviction-scaled sigma."""
    if not (resid_sd and resid_sd > 0 and sxx and sxx > 0 and n and n >= 3):
        return None
    return resid_sd * math.sqrt(1.0 / n + (alpha - alpha_mean) * (alpha - alpha_mean) / sxx)


def conviction_sigma(base_sigma, z, floor=0.2, full=1.5):
    """Fallback effective forecast sigma that grows as conviction shrinks: sigma = base / clamp(|z|/full, floor, 1).
    At |z|>=full (HIGH) -> base; at |z|->0 -> base/floor (max uncertainty). Used only when no per-name SE exists."""
    rel = abs(z) / full if full > 0 else 0.0
    rel = max(floor, min(1.0, rel))
    return base_sigma / rel


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


def stein_shrink(x, se, tau, center=0.0):
    """Empirical-Bayes / James-Stein shrinkage of a noisy estimate toward `center`: w = tau^2/(tau^2+se^2);
    shrunk = center + w*(x-center). Noisier estimates (large se) shrink harder toward the center. Use the
    cross-sectional mean as the center to BORROW STRENGTH across names; center=0 reproduces shrink-to-zero."""
    if se is None or se <= 0 or tau is None or tau <= 0:
        return x
    w = (tau * tau) / (tau * tau + se * se)
    return center + w * (x - center)


def ewma_score(prev, now, lam=0.5):
    """Run-over-run smoothing for rank stability (damps daily whipsaw). lam in (0,1]; prev None -> now."""
    if prev is None or prev != prev:
        return now
    return lam * now + (1.0 - lam) * prev


def composite_rank_score(tot, z, base_sigma, k=0.5, n_tests=None, prev=None, lam=1.0, se=None):
    """Headline ranking score the board sorts by:
      1. sigma = per-name regression SE `se` when supplied (the genuine estimation uncertainty); otherwise
         the conviction-scaled proxy conviction_sigma(base_sigma, z).
      2. LCB: shift `tot` toward 0 by k*sigma in the direction of its sign (lcb_score).
      3. Multiplicity: when n_tests is supplied, apply a SOFT selection discount min(1, |z|/sqrt(2 ln n)) so a
         name that has not cleared the cross-sectional bar cannot present full strength. This is separate from
         the estimation-noise LCB (different source of doubt: selection vs. measurement).
      4. EWMA-smooth against the prior run's score when `prev` is supplied."""
    sigma = se if (se is not None and se == se and se > 0) else conviction_sigma(base_sigma, z)
    s = lcb_score(tot, sigma, k)
    if n_tests is not None and n_tests >= 2:
        bar = math.sqrt(2.0 * math.log(n_tests))
        if bar > 0:
            s = s * min(1.0, abs(z) / bar)
    return ewma_score(prev, s, lam) if (prev is not None) else s


# ---- committed golden fixture (both languages lock to it) ----
def gen_fixture():
    cases = [
        {"tot": 6.5, "z": 2.1, "base_sigma": 9.0, "se": 1.2},   # high edge, high conviction, clean estimate
        {"tot": 6.0, "z": 0.5, "base_sigma": 9.0, "se": 4.5},   # high edge, LOW conviction + noisy -> ranks lower
        {"tot": -5.0, "z": -1.8, "base_sigma": 9.0, "se": 1.5}, # bear, high conviction
        {"tot": -4.8, "z": -0.4, "base_sigma": 9.0, "se": 3.8}, # bear, low conviction + noisy
        {"tot": 1.2, "z": 3.0, "base_sigma": 6.0, "se": 0.6},   # small edge, very high conviction, very clean
    ]
    n = len(cases)
    out = []
    for c in cases:
        out.append({
            "tot": c["tot"], "z": c["z"], "base_sigma": c["base_sigma"], "se": c["se"],
            "convSigma": conviction_sigma(c["base_sigma"], c["z"]),
            "lcb": lcb_score(c["tot"], c["se"], 0.5),
            "score": composite_rank_score(c["tot"], c["z"], c["base_sigma"], 0.5, n, se=c["se"]),
            "zAdj": deflated_conviction(c["z"], 150),
            "gk": grinold_kahn(0.08, c["base_sigma"], c["z"]),
            "aFse": alpha_forecast_se(2.0, c["z"], 0.0, 10.0, n),     # leverage SE with z as a stand-in alpha
            "steinC": stein_shrink(c["tot"], c["se"], 3.0, center=1.0),
        })
    return {"fixture_version": 2, "case": "rank-engine-core", "k": 0.5, "n_tests": n, "rows": out}


def main():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rank_golden.json")
    json.dump(gen_fixture(), open(p, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(p))


if __name__ == "__main__":
    main()
