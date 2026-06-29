import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj_engine as P

def test_decay_multiplier():
    assert abs(P.cumulative_decay_multiplier(1, 3) - 1.0) < 1e-12          # M(1)=1
    assert P.cumulative_decay_multiplier(10, 3) > P.cumulative_decay_multiplier(5, 3)  # increasing in H
    assert abs(P.cumulative_decay_multiplier(10, 1e9) - 10.0) < 1e-3       # tau->inf -> H
    print("  PASS  decay multiplier: M(1)=1, increasing in H, ->H as tau->inf")

def test_path_normalizes_to_forecast():
    pj = P.build_fallback_projection(199.50, 205.80, 0.022, 21, half_life=3)
    # expected path at e=H equals the stored forecast
    pH = P.expected_path_price(199.50, pj["muH"], 21, 21, 3)
    assert abs(pH - pj["projCloseFwdH"]) < 1e-6, (pH, pj["projCloseFwdH"])
    # at e=0 -> priceNow
    assert abs(P.expected_path_price(199.50, pj["muH"], 0, 21, 3) - 199.50) < 1e-9
    print("  PASS  expected-path normalized: path(H)=stored forecast, path(0)=priceNow")

def test_aapl_golden_case():
    # PDF golden: AAPL H=21, priceNow 199.50, projClose 205.80, actual 203.90, sigma_daily 0.022
    sigma_H = 0.022 * math.sqrt(21)
    sc = P.score_accuracy(203.90, 205.80, sigma_H)
    assert abs(sigma_H - 0.10082) < 1e-4, sigma_H
    assert abs(sc["signedLogError"] - (-0.00928)) < 1e-4, sc["signedLogError"]
    assert abs(sc["signedZError"] - (-0.0920)) < 1e-3, sc["signedZError"]
    print("  PASS  AAPL golden: sigmaH=%.4f, signedLogError=%.5f, zErr=%.3f (Excellent)" % (sigma_H, sc["signedLogError"], sc["signedZError"]))

def test_skill_vs_naive():
    # perfect forecaster -> skill 1 ; forecast==naive -> skill 0
    act = [101.0, 99.0, 103.0]; pn = [100.0, 100.0, 100.0]
    assert P.skill_vs_naive(act, act, pn) > 0.999
    assert abs(P.skill_vs_naive(pn, act, pn)) < 1e-9
    print("  PASS  skill-vs-naive: perfect->1, naive->0")

def test_prob_above():
    assert P.prob_above_now(0.10, 0.10) > 0.8 and abs(P.prob_above_now(0, 0.1) - 0.5) < 1e-9
    print("  PASS  prob_above_now = Phi(muH/sigmaH)")

if __name__ == "__main__":
    test_decay_multiplier(); test_path_normalizes_to_forecast(); test_aapl_golden_case(); test_skill_vs_naive(); test_prob_above()
    print("\nALL PROJ ENGINE TESTS PASSED")
