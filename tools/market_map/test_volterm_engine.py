"""Planted tests: random walk -> VR~1 & HV~sqrt; mean-reverting -> VR<1 & HV<sqrt; persistent -> VR>1 &
HV>sqrt. EWMA tracks a vol shift. blended_scale renormalizes."""
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import volterm_engine as V

def _rw(seed, T=4000, sd=0.01):
    rng = random.Random(seed); return [rng.gauss(0, sd) for _ in range(T)]

def _ar1(seed, phi, T=4000, sd=0.01):
    rng = random.Random(seed); r = []; prev = 0.0
    for _ in range(T):
        e = rng.gauss(0, sd); x = phi * prev + e; r.append(x); prev = x
    return r

def test_random_walk_vr_near_one():
    r = _rw(1)
    for q in (2, 5, 10):
        vr = V.variance_ratio(r, q)
        assert abs(vr["vr"] - 1.0) < 0.12, (q, vr["vr"])
        assert vr["ciLo"] < 1.0 < vr["ciHi"], vr      # 1.0 inside the robust CI
    # HV term structure ~ sqrt baseline for a random walk
    H = [1, 5, 10, 30]
    hv = V.hv_term_structure(r, H); sq = V.sqrt_baseline(r, H)
    for h in (5, 10, 30):
        assert abs(hv[h] / sq[h] - 1.0) < 0.15, (h, hv[h], sq[h])
    print("  PASS  random walk: VR(q)~1 (1.0 in CI), HV term structure ~ sqrt baseline")

def test_mean_reverting_vr_below_one():
    r = _ar1(2, phi=-0.4)
    vr = V.variance_ratio(r, 2)
    assert vr["vr"] < 0.9, vr["vr"]
    assert vr["zRobust"] < -2.0, vr["zRobust"]        # significantly < 1
    hv = V.hv_term_structure(r, [1, 2]); sq = V.sqrt_baseline(r, [1, 2])
    assert hv[2] < sq[2], (hv[2], sq[2])              # sqrt OVERstates short-horizon vol
    print("  PASS  mean-reverting (phi=-0.4): VR(2)=%.3f<1, z*=%.2f, HV<sqrt" % (vr["vr"], vr["zRobust"]))

def test_persistent_vr_above_one():
    r = _ar1(3, phi=0.4)
    vr = V.variance_ratio(r, 5)
    assert vr["vr"] > 1.1, vr["vr"]
    assert vr["zRobust"] > 2.0, vr["zRobust"]
    hv = V.hv_term_structure(r, [1, 5]); sq = V.sqrt_baseline(r, [1, 5])
    assert hv[5] > sq[5], (hv[5], sq[5])              # sqrt UNDERstates
    print("  PASS  persistent (phi=+0.4): VR(5)=%.3f>1, z*=%.2f, HV>sqrt" % (vr["vr"], vr["zRobust"]))

def test_ewma_tracks_vol_shift():
    rng = random.Random(9)
    calm = [rng.gauss(0, 0.005) for _ in range(500)]
    storm = [rng.gauss(0, 0.03) for _ in range(200)]
    s_calm = V.ewma_vol(calm, 0.94)
    s_storm = V.ewma_vol(calm + storm, 0.94)
    assert s_storm > 2.5 * s_calm, (s_calm, s_storm)
    print("  PASS  EWMA vol jumps after a 6x variance shift (%.4f -> %.4f)" % (s_calm, s_storm))

def test_blended_scale_renormalizes():
    s = V.blended_scale({"hv": 0.10, "ewma": 0.20, "garch": None}, {"hv": 1, "ewma": 1, "garch": 1}, 5)
    # equal weight over the two present -> sqrt(mean of variances)
    assert abs(s - math.sqrt((0.10**2 + 0.20**2) / 2)) < 1e-12, s
    print("  PASS  blended_scale renormalizes over present components (%.5f)" % s)

def test_studentize():
    assert abs(V.studentize(0.02, 0.00, 0.10) - 0.2) < 1e-4
    print("  PASS  studentize scales residual by sigma_H")

if __name__ == "__main__":
    test_random_walk_vr_near_one(); test_mean_reverting_vr_below_one(); test_persistent_vr_above_one()
    test_ewma_tracks_vol_shift(); test_blended_scale_renormalizes(); test_studentize()
    print("\nALL VOLTERM ENGINE TESTS PASSED")
