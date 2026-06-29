"""Planted tests for beta_adjust.py (Dimson + Vasicek + Bloomberg)."""
import random, math
import beta_adjust as BA

def test_ols_recovers_planted_beta():
    random.seed(1)
    mkt = [random.gauss(0, 0.01) for _ in range(400)]
    y = [1.3 * m + random.gauss(0, 0.002) for m in mkt]   # true beta 1.3, low noise
    b, se = BA.ols_beta_se(y, mkt)
    assert abs(b - 1.3) < 0.05 and se > 0, (b, se)

def test_dimson_recovers_lagged_loading():
    random.seed(2)
    mkt = [random.gauss(0, 0.01) for _ in range(500)]
    # non-synchronous: stock reacts 0.6 today + 0.6 to yesterday's market -> true summed beta ~1.2
    y = [0.0] * len(mkt)
    for t in range(1, len(mkt)):
        y[t] = 0.6 * mkt[t] + 0.6 * mkt[t - 1] + random.gauss(0, 0.001)
    contemp, _ = BA.ols_beta_se(y[1:], mkt[1:])
    dim = BA.dimson_beta(y, mkt, lags=1, leads=1)
    assert dim > contemp + 0.2, (contemp, dim)            # Dimson recovers the lagged piece OLS misses
    assert abs(dim - 1.2) < 0.2, dim

def test_vasicek_shrinks_noisy_more():
    # a DISPERSED cross-section (so var_cross>0) with two names sharing raw beta 1.8 but different SE.
    betas = [0.6, 1.0, 1.4, 1.8, 1.8]
    ses   = [0.10, 0.10, 0.10, 0.05, 0.80]   # last name (1.8) is very noisy
    out = BA.vasicek(betas, ses, prior=1.0)
    # the precise 1.8 (idx 3) stays near 1.8; the noisy 1.8 (idx 4) is pulled harder toward the prior
    assert abs(out[3] - 1.8) < abs(out[4] - 1.8), out
    assert out[4] < out[3]

def test_bloomberg_two_thirds():
    assert abs(BA.bloomberg_adjust(1.9) - (2/3*1.9 + 1/3*1.0)) < 1e-9

if __name__ == "__main__":
    test_ols_recovers_planted_beta(); test_dimson_recovers_lagged_loading()
    test_vasicek_shrinks_noisy_more(); test_bloomberg_two_thirds()
    print("test_beta_adjust: 4/4 PASS")
