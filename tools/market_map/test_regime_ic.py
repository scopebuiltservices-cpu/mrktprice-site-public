import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_ic as R

def _two_regime(seed, T=1200):
    rng = random.Random(seed); x = []; truth = []; s = 0
    for _ in range(T):
        s = s if rng.random() < 0.97 else 1 - s          # sticky regimes
        truth.append(s)
        x.append(rng.gauss(0, 0.005 if s == 0 else 0.02))  # calm vs stress vol
    return x, truth

def test_hmm_separates_regimes():
    x, truth = _two_regime(1)
    h = R.gaussian_hmm_2state(x)
    assert h["var"][1] > 3 * h["var"][0], h["var"]                  # state1 clearly higher variance
    path = R.viterbi_path(x, h)
    agree = sum(1 for t in range(len(truth)) if path[t] == truth[t]) / len(truth)
    agree = max(agree, 1 - agree)                                    # label-invariant
    assert agree > 0.8, agree
    print("  PASS  2-state HMM separates calm/stress (var ratio %.1fx, path agreement %.0f%%)" % (h["var"][1]/h["var"][0], agree*100))

def test_regime_ic_recovers_state_skill():
    # IC positive in state 0, negative in state 1
    path = [0, 0, 1, 1, 0, 1, 0, 1]
    ic = [{"mom": 0.1}, {"mom": 0.12}, {"mom": -0.08}, {"mom": -0.1}, {"mom": 0.09}, {"mom": -0.11}, {"mom": 0.08}, {"mom": -0.09}]
    ri = R.regime_ic(ic, path, ["mom"])
    assert ri[0]["mom"] > 0.08 and ri[1]["mom"] < -0.08, ri
    mu0 = R.state_conditioned_mu(0, ri, 0.02, 1.5, "mom")
    mu1 = R.state_conditioned_mu(1, ri, 0.02, 1.5, "mom")
    assert mu0 > 0 > mu1
    print("  PASS  regime-IC: state0 +%.3f / state1 %.3f; mu flips sign by regime" % (ri[0]["mom"], ri[1]["mom"]))

if __name__ == "__main__":
    test_hmm_separates_regimes(); test_regime_ic_recovers_state_skill()
    print("\nALL REGIME_IC TESTS PASSED")
