"""Planted tests: MZ removes bias, shrinks a noisy forecast (β<1), perfect->skill=1, naive->skill=0."""
import sys, os, random, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projlearn_engine as P

def test_bias_removed():
    rng = random.Random(1); N = 300
    real = [rng.gauss(0, 0.04) for _ in range(N)]
    pred = [r + 0.02 for r in real]                       # systematically +2% too high
    mz = P.mincer_zarnowitz(pred, real)
    assert abs(mz["alpha"] + 0.02) < 0.005 and abs(mz["beta"] - 1.0) < 0.05, mz
    rec = [P.recalibrate(p, mz["alpha"], mz["beta"]) for p in pred]
    assert abs(P.bias(rec, real)) < abs(P.bias(pred, real)) and abs(P.bias(rec, real)) < 0.003
    print("  PASS  MZ recovers α≈−0.02, β≈1; recalibration removes the bias (%.4f -> %.4f)"
          % (P.bias(pred, real), P.bias(rec, real)))

def test_shrinks_noisy():
    rng = random.Random(2); N = 400
    true = [rng.gauss(0, 0.03) for _ in range(N)]
    real = true[:]
    pred = [t + rng.gauss(0, 0.05) for t in true]          # forecast = truth + big noise
    mz = P.mincer_zarnowitz(pred, real)
    assert mz["beta"] < 0.7, mz["beta"]                    # β shrinks below 1 (too aggressive raw)
    print("  PASS  noisy forecast -> β=%.2f < 1 (recalibration shrinks toward no-change)" % mz["beta"])

def test_perfect_and_naive_skill():
    rng = random.Random(3); N = 200
    real = [rng.gauss(0, 0.04) for _ in range(N)]
    assert P.skill_vs_naive(real, real) > 0.999 and P.theil_u2(real, real) < 0.001     # perfect
    assert abs(P.skill_vs_naive([0.0] * N, real)) < 1e-9 and abs(P.theil_u2([0.0] * N, real) - 1) < 1e-9  # naive
    print("  PASS  skill: perfect forecaster->1 (U2->0); naive (predLR=0)->0 (U2->1)")

def test_learn_shrinkage_grows():
    rng = random.Random(4)
    real = [rng.gauss(0, 0.03) for _ in range(50)]
    pred = [r * 0.8 + rng.gauss(0, 0.01) for r in real]
    small = P.learn(pred[:6], real[:6]); big = P.learn(pred, real)
    assert not small["applied"] and big["applied"]          # gated until n_min
    assert big["shrink"] > small["shrink"]                  # correction strengthens with n
    assert abs(small["wBeta"] - 1.0) < 0.12                  # tiny-n correction ~ identity (safe)
    print("  PASS  learn(): gated until n_min, shrink grows %.2f->%.2f, correction strengthens"
          % (small["shrink"], big["shrink"]))

def test_coverage():
    real = [0.0, 0.05, -0.05, 0.2]
    lo = [-0.1, -0.1, -0.1, -0.1]; hi = [0.1, 0.1, 0.1, 0.1]
    assert abs(P.coverage(real, lo, hi) - 0.75) < 1e-9      # the 0.2 is outside
    print("  PASS  coverage: 3/4 inside -> 0.75")

if __name__ == "__main__":
    test_bias_removed(); test_shrinks_noisy(); test_perfect_and_naive_skill(); test_learn_shrinkage_grows(); test_coverage()
    print("\nALL PROJLEARN ENGINE TESTS PASSED")
