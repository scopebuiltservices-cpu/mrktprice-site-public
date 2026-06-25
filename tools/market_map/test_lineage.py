"""Unit tests for lineage.py — every estimator checked against planted structure."""
import math, random
import lineage as L


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_viterbi_recovers_planted_path():
    # 2 regimes; obs strongly favor planted path [0,0,1,1,1]
    K = 2
    log_init = [math.log(0.5)] * K
    # sticky transitions
    tr = [[0.9, 0.1], [0.1, 0.9]]
    log_trans = [[math.log(x) for x in row] for row in tr]
    planted = [0, 0, 1, 1, 1]
    log_lik = []
    for z in planted:
        row = [math.log(0.05), math.log(0.05)]
        row[z] = math.log(0.95)
        log_lik.append(row)
    out = L.viterbi(log_init, log_trans, log_lik)
    assert out["path"] == planted, out["path"]


def test_top_branches_orders_and_normalizes():
    post = [0.6, 0.3, 0.1]
    trans = [[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.2, 0.2, 0.6]]
    b = L.top_branches(post, trans, k=3)
    assert b[0]["regime"] == 0          # highest posterior * self-transition
    assert abs(sum(x["p"] for x in b) - 1.0) < 1e-9
    assert b[0]["p"] >= b[1]["p"] >= b[2]["p"]


def test_branch_decomposition_total_variance():
    # planted: two regimes, equal weight, means +/-2, within var 1 each
    w = [0.5, 0.5]
    means = [2.0, -2.0]
    varz = [1.0, 1.0]
    d = L.branch_decomposition(w, means, varz)
    assert approx(d["within"], 1.0)      # E[Var] = 1
    assert approx(d["between"], 4.0)     # Var(E) = 0.5*4 + 0.5*4 = 4
    assert approx(d["total"], 5.0)
    assert approx(d["diffusive_share"], 0.2)
    assert approx(d["branching_share"], 0.8)


def test_bridge_touch_monotone_and_bounds():
    var_dt = 0.04
    # closer barrier -> higher touch prob
    near = L.bridge_touch_upper(0.0, 0.0, 0.05, var_dt)
    far = L.bridge_touch_upper(0.0, 0.0, 0.30, var_dt)
    assert 0.0 <= far < near <= 1.0
    # barrier already breached by an endpoint -> certain
    assert L.bridge_touch_upper(0.0, 0.10, 0.05, var_dt) == 1.0
    assert L.bridge_touch_lower(0.0, -0.10, -0.05, var_dt) == 1.0
    # symmetry: lower mirror of upper
    up = L.bridge_touch_upper(0.0, 0.0, 0.06, var_dt)
    dn = L.bridge_touch_lower(0.0, 0.0, -0.06, var_dt)
    assert approx(up, dn)


def test_sigma_volume_matrix_bins():
    paths = [{"horizon": "1d", "retZ": 0.5, "cumVol": 100},
             {"horizon": "1d", "retZ": 1.5, "cumVol": 300},
             {"horizon": "1d", "retZ": 1.7, "cumVol": 500},
             {"horizon": "5d", "retZ": -0.5, "cumVol": 50}]
    m = L.sigma_volume_matrix(paths, ["1d", "5d"], [0, 1, 2])
    assert m["1d"]["0..1"]["n"] == 1 and approx(m["1d"]["0..1"]["meanCumVol"], 100)
    assert m["1d"]["1..2"]["n"] == 2 and approx(m["1d"]["1..2"]["meanCumVol"], 400)  # (300+500)/2
    assert m["5d"]["0..1"]["meanCumVol"] is None   # -0.5 not in [0,2)


def test_conformal_coverage_marginal():
    # split conformal should give ~ (1-alpha) marginal coverage on exchangeable data
    random.seed(7)
    alpha = 0.10
    n = 2000
    cal = [random.gauss(0, 1) for _ in range(n)]
    # model interval naive [-1,1]; conformal should widen to ~ +/-1.64
    pad = L.conformal_pad([max(-1 - y, y - 1, 0.0) for y in cal], alpha)
    lo, hi = -1 - pad, 1 + pad
    test = [random.gauss(0, 1) for _ in range(20000)]
    cov = sum(1 for y in test if lo <= y <= hi) / len(test)
    assert cov >= 1 - alpha - 0.02, cov   # finite-sample marginal coverage holds


def test_straddle_labels_ratio():
    s0, sig, T = 100.0, 0.20, 0.25
    lab = L.straddle_labels(s0, sig, T)
    # sigma-equivalent should be sqrt(pi/2) * implied-abs-move, and == model 1-sigma
    assert approx(lab["sigmaEquivMove"], lab["impliedAbsMove"] * math.sqrt(math.pi / 2))
    assert approx(lab["sigmaEquivMove"], lab["sigma1Move"], tol=1e-9)
    assert lab["impliedAbsMove"] < lab["sigmaEquivMove"]   # E|move| < 1-sigma move


def test_event_variance_and_house_blend():
    # base var 0.01/yr over 0.1yr = 0.001; implied bump 0.0025 -> event var 0.0015
    ev = L.event_variance(w_q_plus=0.0040, w_q_minus=0.0015, base_var_per_t=0.01, dt_span=0.10)
    assert approx(ev, 0.0040 - 0.0015 - 0.001)
    hb = L.house_blend(sig_q2=0.04, sig_p2=0.02, v_evt=0.001, omega_q=0.5)
    assert approx(hb, 0.5 * 0.04 + 0.5 * 0.02 + 0.001)
    # bad liquidity -> omega_Q 0 -> pure P + event
    assert approx(L.house_blend(0.04, 0.02, 0.0, 0.0), 0.02)


def test_hawkes_expected_count_positive_and_clusters():
    base = L.hawkes_expected_count(100.0, [], mu_per_min=2.0, alpha=1.0, beta_per_min=0.5, horizon_min=10)
    excited = L.hawkes_expected_count(100.0, [99.0, 99.5], mu_per_min=2.0, alpha=1.0, beta_per_min=0.5, horizon_min=10)
    assert approx(base["expectedCount"], 20.0)        # mu*horizon
    assert excited["expectedCount"] > base["expectedCount"]   # recent events raise it
    assert excited["lambdaNow"] > base["lambdaNow"]


def test_driver_label_discipline_and_reasoning():
    drv = L.driver_contributions([0.7, 0.3], betas=[2.0, -1.0, 0.5],
                                 dfactors=[1.0, 2.0, 0.1],
                                 names=["10Y", "WTI", "VIX"],
                                 labels=["associated", "event-linked", "bogus"])
    assert abs(sum(d["contrib"] for d in drv) - 1.0) < 1e-9
    assert drv[0]["contrib"] >= drv[1]["contrib"] >= drv[2]["contrib"]
    assert drv[2]["label"] == "associated"   # 'bogus' coerced to safe default
    node = L.LineageNode(node_id="n1", parent_id=None, forecast_ts="t0", horizon_end_ts="t1",
                         horizon="1d", q10=95, q25=97, q50=100, q75=103, q90=105, q95=107,
                         p_node=0.42, p_touch_up=0.3, p_touch_down=0.2,
                         expected_cum_volume=1_250_000, drivers_ranked=drv,
                         confidence_decomp={"branching_share": 0.6, "diffusive_share": 0.4})
    txt = L.reasoning_from_fields(node)
    assert "median 100.00" in txt and "42%" in txt and "10Y" in txt


def test_gaussian_hmm_recovers_planted_regimes():
    random.seed(11)
    params = {0: (-0.02, 0.03), 1: (0.015, 0.01)}
    z, x = 1, []
    for _ in range(600):
        z = z if random.random() < 0.92 else 1 - z
        mu, sd = params[z]
        x.append(random.gauss(mu, sd))
    fit = L.gaussian_hmm_fit(x, K=2)
    assert fit["ok"]
    assert fit["means"][0] < fit["means"][1]
    assert abs(fit["means"][0] - (-0.02)) < 0.012, fit["means"]
    assert abs(fit["means"][1] - 0.015) < 0.012, fit["means"]
    assert fit["vars"][1] < fit["vars"][0]
    assert fit["trans"][0][0] > 0.7 and fit["trans"][1][1] > 0.7


def test_lineage_object_shape_and_decomposition():
    random.seed(12)
    z, x = 0, []
    for _ in range(400):
        z = z if random.random() < 0.9 else 1 - z
        x.append(random.gauss(-0.02 if z == 0 else 0.02, 0.02))
    lo = L.lineage_object(x)
    assert lo is not None
    assert lo["K"] == 2 and len(lo["post"]) == 2
    assert abs(sum(lo["post"]) - 1.0) < 1e-6
    assert abs(sum(b["p"] for b in lo["branches"]) - 1.0) < 1e-6
    for label, _d, _p in L.PRIMARY_HORIZONS:
        h = lo["horizons"][label]
        assert abs(h["diffusive"] + h["branching"] - 1.0) < 1e-3, (label, h)
        assert h["totVol"] >= 0 and h["mapVol"] >= 0
    assert lo["horizons"]["5d"]["branching"] >= lo["horizons"]["intraday"]["branching"] - 1e-6


def test_crps_gaussian_closed_form():
    # CRPS of N(0,1) at y=0 == 2*phi(0) - 1/sqrt(pi) == 1/sqrt(pi)*(... ) known value ~0.2336
    import math
    c = L.crps_gaussian(0.0, 0.0, 1.0)
    expected = 2 * (1 / math.sqrt(2 * math.pi)) - 1 / math.sqrt(math.pi)  # = 0.23369...
    assert approx(c, expected, 1e-9), (c, expected)
    # CRPS scales with sigma and is minimized at y=mu
    assert L.crps_gaussian(0, 0, 2.0) > L.crps_gaussian(0, 0, 1.0)
    assert L.crps_gaussian(5, 0, 1.0) > L.crps_gaussian(0, 0, 1.0)


def test_wilson_interval_known():
    lo, hi = L.wilson_interval(50, 100)        # p=0.5, n=100
    assert lo < 0.5 < hi and approx((lo + hi) / 2, 0.5, 0.01)
    # tighter than Wald would be near edges; for k=n it must not exceed 1
    lo2, hi2 = L.wilson_interval(100, 100)
    assert hi2 <= 1.0 and lo2 < 1.0
    # wider with smaller n
    lo3, hi3 = L.wilson_interval(5, 10)
    assert (hi3 - lo3) > (hi - lo)


def test_interval_score_penalties():
    # inside interval -> just width; below -> width + (2/alpha)(lo-y)
    a = 0.10
    inside = L.interval_score(0.0, -1, 1, a)
    below = L.interval_score(-2.0, -1, 1, a)
    assert approx(inside, 2.0)
    assert approx(below, 2.0 + (2 / a) * (-1 - (-2.0)))   # 2 + 20*1 = 22
    assert below > inside


def test_pit_uniform_vs_skewed():
    import random
    random.seed(3)
    uni = [random.random() for _ in range(2000)]
    sk = [random.random() ** 2 for _ in range(2000)]   # not uniform
    ku = L.pit_ks(uni); ks = L.pit_ks(sk)
    assert ku["p"] > 0.05            # uniform PIT not rejected
    assert ks["p"] < 0.05            # skewed PIT rejected
    assert ks["D"] > ku["D"]


def test_dkw_shrinks_with_n():
    assert L.dkw_band(100) > L.dkw_band(10000)
    assert L.dkw_band(0) is None


def test_calibrate_horizon_correct_model_hits_target():
    # i.i.d. N(0, s) returns -> the rolling-Gaussian predictive is correctly specified,
    # so empirical coverage of the 90% band should be ~0.90 (within Wilson CI of target).
    import random
    random.seed(5)
    r = [random.gauss(0.0005, 0.02) for _ in range(700)]
    c = L.calibrate_horizon(r, n_steps=1, window=40, alpha=0.10)
    assert c is not None
    assert c["target"] == 0.90
    assert c["wilsonLo"] <= 0.90 <= c["wilsonHi"], (c["coverage"], c["wilsonLo"], c["wilsonHi"])
    assert c["crps"] > 0 and c["intervalScore"] > 0
    # conformal pad should be small for an already-calibrated model
    assert c["coveragePadded"] >= c["coverage"] - 1e-9


def test_validation_snapshot_per_horizon():
    import random
    random.seed(6)
    z, x = 0, []
    for _ in range(500):
        z = z if random.random() < 0.9 else 1 - z
        x.append(random.gauss(-0.01 if z == 0 else 0.01, 0.02))
    fit = L.gaussian_hmm_fit(x, K=2)
    vs = L.validation_snapshot(x, fit)
    assert "5d" in vs and "20d" in vs
    for label, c in vs.items():
        assert 0.0 <= c["coverage"] <= 1.0
        assert c["wilsonLo"] <= c["coverage"] <= c["wilsonHi"] + 1e-9
        assert c["conformalPad"] >= 0


def test_first_passage_reflection_principle():
    import math
    # driftless: P(touch a) = 2*Phi(-a/sigma)
    a, sig = 0.05, 0.05
    assert approx(L.first_passage_up(a, 0.0, sig), 2 * L.norm_cdf(-a / sig), 1e-9)
    # monotone: closer barrier -> higher touch prob
    assert L.first_passage_up(0.02, 0, sig) > L.first_passage_up(0.10, 0, sig)
    # bounds + already-through
    assert L.first_passage_up(0.0, 0, sig) == 1.0
    assert 0.0 <= L.first_passage_up(0.08, 0.001, sig) <= 1.0
    # down is the mirror of up
    assert approx(L.first_passage_down(-a, 0.0, sig), L.first_passage_up(a, 0.0, sig))
    # upward drift raises an upper touch, lowers a lower touch
    assert L.first_passage_up(0.05, 0.02, sig) > L.first_passage_up(0.05, -0.02, sig)


def test_volume_ahead_conditioning():
    import random, math
    random.seed(21)
    # build daily rows where volume scales with |return| -> big moves carry big volume
    px = 100.0; rows = []
    base = 1_000_000
    for d in range(400):
        r = random.gauss(0, 0.02)
        px *= math.exp(r)
        vol = int(base * (1 + 6 * abs(r) / 0.02))   # |move| in sigma -> volume multiplier
        rows.append(["2020-01-%02d" % (d % 28 + 1), round(px, 4), vol])
    va = L.volume_ahead(rows)
    sv = va["sigvol"]["1d"]
    # outer |z| bin should carry more volume than the center bin
    center = sv["0..1"]["meanCumVol"]
    outer = sv["2..3"]["meanCumVol"]
    assert center is not None and outer is not None and outer > center, (center, outer)
    assert va["base"]["avgVol20"] and va["base"]["dailySigma"] > 0
    assert va["base"]["volAcf1"] is not None


def test_touch_odds_structure():
    import random, math
    random.seed(22)
    px = 100.0; rows = []
    for d in range(120):
        px *= math.exp(random.gauss(0, 0.015))
        rows.append(["2020-01-%02d" % (d % 28 + 1), round(px, 4), 1000])
    to = L.touch_odds(rows)
    assert "5d" in to and "20d" in to
    for label, c in to.items():
        assert 0.0 <= c["pUp"] <= 1.0 and 0.0 <= c["pDn"] <= 1.0
        assert c["levelHigh"] >= c["S"] >= 0 and c["levelLow"] <= c["levelHigh"]
    # longer horizon -> higher chance of touching the recent extreme
    assert to["20d"]["pUp"] >= to["1d"]["pUp"] - 1e-9


def test_lineage_per_regime_drift_vol():
    import random
    random.seed(31)
    z, x = 0, []
    for _ in range(400):
        z = z if random.random() < 0.9 else 1 - z
        x.append(random.gauss(-0.02 if z == 0 else 0.02, 0.02))
    lo = L.lineage_object(x)
    for label, _d, _p in L.PRIMARY_HORIZONS:
        h = lo["horizons"][label]
        assert "rd" in h and "rv" in h and len(h["rd"]) == lo["K"] and len(h["rv"]) == lo["K"]
        # the MAP regime's per-regime drift/vol must equal the published mapDrift/mapVol
        mapk = lo["branches"][0]["regime"]
        assert abs(h["rd"][mapk] - h["mapDrift"]) < 1e-9
        assert abs(h["rv"][mapk] - h["mapVol"]) < 1e-9
        assert all(v >= 0 for v in h["rv"])


if __name__ == "__main__":
    _fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for _f in _fns:
        _f(); print("PASS", _f.__name__)
    print("\nALL %d LINEAGE TESTS PASSED" % len(_fns))
