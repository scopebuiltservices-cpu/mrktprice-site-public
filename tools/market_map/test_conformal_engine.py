"""Planted tests for conformal_engine: CQR restores >=1-alpha marginal coverage on held-out data even
when the base quantile model is deliberately miscalibrated (too tight) under heteroskedasticity."""
import sys, math, random
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conformal_engine as C

def _data(seed, n):
    rng = random.Random(seed)
    xs, ys = [], []
    for _ in range(n):
        x = rng.uniform(0, 1)
        sd = 0.5 + 2.5 * x                      # heteroskedastic noise
        ys.append(rng.gauss(0.0, sd))
        xs.append(x)
    return xs, ys

def _undercover_band(xs, frac=0.5):
    """A base model that knows the conditional sd up to a factor `frac` (<1 -> deliberately too tight)."""
    lo, hi = [], []
    z = C._norm_ppf(0.95)                        # nominal 90% band
    for x in xs:
        sd = (0.5 + 2.5 * x) * frac
        lo.append(-z * sd); hi.append(z * sd)
    return lo, hi

def test_cqr_restores_coverage():
    alpha = 0.10
    fails_naive = 0
    cov_naive_sum = cov_cqr_sum = 0.0
    seeds = 40
    for s in range(seeds):
        xs, ys = _data(s, 1200)
        # split cal/test
        cut = 600
        cqlo, cqhi = _undercover_band(xs[:cut]); cy = ys[:cut]
        tqlo, tqhi = _undercover_band(xs[cut:]); ty = ys[cut:]
        # naive (no conformal) coverage of the too-tight band
        cov_naive = C.interval_coverage(ty, tqlo, tqhi)
        cov_naive_sum += cov_naive
        if cov_naive < 1 - alpha - 0.02:
            fails_naive += 1
        # CQR-conformalized
        lo, hi, pad = C.cqr_calibrate_apply(cqlo, cqhi, cy, tqlo, tqhi, alpha)
        cov_cqr = C.interval_coverage(ty, lo, hi)
        cov_cqr_sum += cov_cqr
        assert cov_cqr >= 1 - alpha - 0.04, f"seed {s}: CQR coverage {cov_cqr:.3f} < target"
    # naive must fail most seeds; CQR must average at/above nominal
    assert fails_naive >= seeds * 0.8, f"naive should undercover, only {fails_naive}/{seeds} did"
    assert cov_cqr_sum / seeds >= 1 - alpha - 0.01
    print(f"  PASS  CQR coverage avg {cov_cqr_sum/seeds:.3f} (naive {cov_naive_sum/seeds:.3f}); naive undercovered {fails_naive}/{seeds}")

def test_cqr_tightens_when_overcovering():
    """If the base band is too WIDE, CQR pad is negative -> tightens toward nominal (efficiency)."""
    alpha = 0.10
    xs, ys = _data(7, 1000)
    cqlo, cqhi = _undercover_band(xs[:500], frac=2.0)   # 2x too wide
    pad = C.cqr_pad(cqlo, cqhi, ys[:500], alpha)
    assert pad < 0, f"pad should be negative for an over-wide band, got {pad:.4f}"
    print(f"  PASS  CQR tightens an over-wide band (pad={pad:.4f} < 0)")

def test_interval_score_prefers_calibrated():
    xs, ys = _data(3, 1000)
    cqlo, cqhi = _undercover_band(xs[:500]); cy = ys[:500]
    tqlo, tqhi = _undercover_band(xs[500:]); ty = ys[500:]
    lo, hi, _ = C.cqr_calibrate_apply(cqlo, cqhi, cy, tqlo, tqhi, 0.10)
    s_naive = C.interval_score(ty, tqlo, tqhi, 0.10)
    s_cqr = C.interval_score(ty, lo, hi, 0.10)
    assert s_cqr < s_naive, f"CQR interval score {s_cqr:.3f} should beat naive {s_naive:.3f}"
    print(f"  PASS  CQR interval score {s_cqr:.3f} < naive {s_naive:.3f}")

def test_finite_sample_too_few_points():
    pad = C.cqr_pad([0.0]*3, [1.0]*3, [0.5]*3, 0.01)   # need ceil(0.99*4)=4 > 3 -> inf
    assert pad == float('inf')
    print("  PASS  too-few-calibration-points -> pad = +inf (honest: cannot guarantee)")

def test_pinball_and_gaussian():
    assert abs(C.pinball_loss(2.0, 1.0, 0.9) - 0.9) < 1e-12
    assert abs(C.pinball_loss(0.0, 1.0, 0.9) - 0.1) < 1e-12
    lo, hi = C.gaussian_quantiles(0.0, 1.0, 0.10)
    assert abs(hi - 1.6448536269514722) < 1e-6 and abs(lo + hi) < 1e-12
    print("  PASS  pinball loss + gaussian_quantiles match closed form")

if __name__ == "__main__":
    test_cqr_restores_coverage()
    test_cqr_tightens_when_overcovering()
    test_interval_score_prefers_calibrated()
    test_finite_sample_too_few_points()
    test_pinball_and_gaussian()
    print("\nALL CONFORMAL ENGINE TESTS PASSED")
