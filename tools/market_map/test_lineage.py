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


if __name__ == "__main__":
    _fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for _f in _fns:
        _f(); print("PASS", _f.__name__)
    print("\nALL %d LINEAGE TESTS PASSED" % len(_fns))
