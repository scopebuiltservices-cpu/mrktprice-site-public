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


def test_pq_layer_scaling_blend_straddle():
    import math
    hz = { "1d": {"totVol": 0.012}, "5d": {"totVol": 0.030}, "20d": {"totVol": 0.060} }
    pq = L.pq_layer(hz, iv_annual=0.20, iv_days=30, earn_days_ahead=4.0, omega_q=0.5)
    assert pq["modellable"] and pq["ivAnnual"] == 0.2 and pq["omegaQ"] == 0.5
    q1, q5 = pq["horizons"]["1d"]["sigQ"], pq["horizons"]["5d"]["sigQ"]
    # sqrt-of-time scaling: sigQ(5d)/sigQ(1d) == sqrt(5)
    assert approx(q5 / q1, math.sqrt(5), 1e-3), (q1, q5)
    # sigQ(1d) == iv*sqrt(1/252)
    assert approx(q1, 0.20 * math.sqrt(1/252), 1e-5)
    # house blend (omega 0.5)
    h5 = pq["horizons"]["5d"]
    assert approx(h5["sigHouse"], math.sqrt(0.5*h5["sigQ"]**2 + 0.5*0.030**2), 1e-6)
    # straddle: sigmaEquiv == impliedAbsMove * sqrt(pi/2)
    assert approx(h5["sigmaEquiv"], h5["impliedAbsMove"] * math.sqrt(math.pi/2), 1e-6)
    # event-in-window: 4 days -> inside 5d (span 7.25), inside 20d, NOT inside 1d (span 1.45)
    assert pq["horizons"]["5d"]["evtIn"] and pq["horizons"]["20d"]["evtIn"]
    assert not pq["horizons"]["1d"]["evtIn"]
    # event share positive when implied > realized (iv 20% annual vs realized ~ here)
    assert h5["eventShare"] is not None and 0 <= h5["eventShare"] <= 1


def test_pq_layer_no_iv_degrades():
    hz = { "5d": {"totVol": 0.03} }
    pq = L.pq_layer(hz, iv_annual=None)
    assert pq["modellable"] is False and pq["ivAnnual"] is None and pq["omegaQ"] == 0.0
    h = pq["horizons"]["5d"]
    assert h["sigQ"] is None and h["sigHouse"] == 0.03 and h["eventShare"] is None


def test_pq_event_share_zero_when_implied_below_realized():
    hz = { "5d": {"totVol": 0.50} }   # huge realized vol, tiny implied
    pq = L.pq_layer(hz, iv_annual=0.10, earn_days_ahead=None)
    assert pq["horizons"]["5d"]["eventShare"] == 0.0   # sigQ <= sigP -> no excess


def test_expected_shortfall_normal():
    import random, math
    random.seed(41)
    r = [random.gauss(0, 1) for _ in range(5000)]
    es = L.expected_shortfall(r, 1, alpha=0.025)
    # ES_2.5% of a standard normal ~ -phi(z)/alpha ~ -2.34
    assert es is not None and es["es"] < es["var"] < 0
    assert -2.7 < es["es"] < -2.0, es["es"]


def test_stressed_es_worse_than_normal():
    import random
    random.seed(42)
    calm = [random.gauss(0, 0.01) for _ in range(300)]
    storm = [random.gauss(0, 0.05) for _ in range(60)]   # high-vol segment
    r = calm[:150] + storm + calm[150:]
    es = L.expected_shortfall(r, 1)
    ses = L.stressed_es(r, 1, win=52)
    assert ses["es"] <= es["es"] + 1e-9   # stressed window ES is at least as severe


def test_challenger_drift_beats_rw():
    import random
    random.seed(43)
    # strong positive drift -> the drift-aware model should beat the zero-drift random walk
    r = [random.gauss(0.01, 0.015) for _ in range(600)]
    sc = L.challenger_scorecard(r, 1, window=40)
    assert sc is not None
    assert sc["crps"]["model"] <= sc["crps"]["rw"]      # model (with drift) wins on CRPS
    assert sc["beatsRW"] is True
    assert sc["gate"] in ("deployable", "research-only")
    assert sc["winner"] in sc["crps"]


def test_challenger_pure_noise_no_edge():
    import random
    random.seed(44)
    r = [random.gauss(0.0, 0.02) for _ in range(600)]   # no drift -> model ~ rw
    sc = L.challenger_scorecard(r, 1, window=40)
    # model and rw should be close; gate must not over-claim deployable falsely on a fluke
    assert abs(sc["crps"]["model"] - sc["crps"]["rw"]) < 0.01


def test_scan_risk_grid():
    sr = L.scan_risk(0.03)
    assert sr["scanRisk"] == round(-3 * 0.03 * 1.3, 4)   # worst = -3sigma under vol-up scenario
    assert len(sr["cells"]) == 3 and len(sr["cells"][0]) == 7
    assert L.scan_risk(None) is None and L.scan_risk(0) is None


def test_simm_decomp():
    sm = L.simm_decomp([{"f": "10Y yield", "sens": -1.3}], sigP=0.03, sigQ=0.034)
    assert sm["delta"]["factor"] == "10Y yield" and sm["delta"]["sensPctPerSigma"] == -1.3
    assert approx(sm["vega"], 0.004, 1e-9)
    assert sm["curvature"] is None


def test_governance_block_assembles():
    import random
    random.seed(45)
    r = [random.gauss(0.002, 0.02) for _ in range(500)]
    lin = {"horizons": {"20d": {"totVol": 0.06}}}
    gov = L.governance_block(r, lin, iv_annual=0.2, gov_horizon="20d")
    assert gov["horizon"] == "20d"
    assert gov["es975"] and gov["stressedES"] and gov["challenger"] and gov["scanRisk"]
    assert gov["releaseGate"] in ("deployable", "research-only", "blocked")
    assert "q" in gov["challenger"]["crps"]   # options-implied challenger present (iv given)


def test_causal_support_labels():
    import random
    random.seed(51)
    n = 400
    f1 = [random.gauss(0, 1) for _ in range(n)]
    # f2 is a confounder: correlated with f1 but NOT a driver of y
    f2 = [0.8 * f1[i] + random.gauss(0, 0.6) for i in range(n)]
    # y is driven ONLY by f1 (causal), plus noise
    y = [2.0 * f1[i] + random.gauss(0, 1.0) for i in range(n)]
    res = L.causal_support(y, {"F1": f1, "F2": f2})
    by = {d["f"]: d for d in res}
    # F1: partialled-out effect ~2, significant + stable -> plausibly-causal
    assert by["F1"]["label"] == "plausibly-causal", by["F1"]
    assert 1.5 < by["F1"]["partial"] < 2.5
    assert by["F1"]["ciLo"] > 0
    # F2: has marginal correlation (via f1) but partial ~0 -> merely-correlative (NOT causal)
    assert by["F2"]["label"] == "merely-correlative", by["F2"]
    assert abs(by["F2"]["partial"]) < 0.5
    assert abs(by["F2"]["marginal"]) > 0.3   # it IS marginally correlated


def test_evt_gpd_heavy_vs_thin_tail():
    import random
    random.seed(52)
    # heavy-tailed (Student-t df=3) -> xi > 0
    def t3():
        # crude t_3 via ratio
        z = random.gauss(0, 1); c = sum(random.gauss(0, 1) ** 2 for _ in range(3))
        return z / math.sqrt(c / 3)
    heavy = [0.01 * t3() for _ in range(2000)]
    thin = [random.uniform(-0.02, 0.02) for _ in range(2000)]
    eh = L.evt_gpd_tail(heavy); et = L.evt_gpd_tail(thin)
    assert eh is not None and et is not None
    assert eh["xi"] > et["xi"]                 # heavy tail has larger shape index
    assert eh["exceedances"] >= 10 and eh["gpdES"] < 0   # ES is a loss (negative)


def test_tail_dependence_comonotone_vs_independent():
    import random
    random.seed(53)
    a = [random.gauss(0, 1) for _ in range(1000)]
    como = a[:]                                  # b == a -> perfect tail dependence
    indep = [random.gauss(0, 1) for _ in range(1000)]
    tc = L.tail_dependence(a, como); ti = L.tail_dependence(a, indep)
    assert approx(tc["lambdaLower"], 1.0, 1e-9) and approx(tc["lambdaUpper"], 1.0, 1e-9)
    assert ti["lambdaLower"] < 0.4 and ti["lambdaUpper"] < 0.4   # ~ q under independence


def test_factor_covariance_and_decomp():
    import random
    random.seed(61)
    n = 300
    f1 = [random.gauss(0, 0.02) for _ in range(n)]
    f2 = [random.gauss(0, 0.015) for _ in range(n)]
    fcov = L.factor_covariance({"F1": f1, "F2": f2})
    assert fcov is not None and fcov["version"].startswith("fcov-")
    assert fcov["cov"][0][0] > 0 and fcov["cov"][1][1] > 0
    assert approx(fcov["cov"][0][1], fcov["cov"][1][0], 1e-12)   # symmetric
    # y = 2*F1 + 0.5*F2 + small idio
    y = [2.0 * f1[i] + 0.5 * f2[i] + random.gauss(0, 0.005) for i in range(n)]
    fd = L.factor_decomp(y, {"F1": f1, "F2": f2}, fcov)
    assert abs(fd["exposures"]["F1"] - 2.0) < 0.3 and abs(fd["exposures"]["F2"] - 0.5) < 0.3
    assert fd["explainedPct"] > 70          # factors explain most variance
    assert approx(fd["totalVar"], fd["factorVar"] + fd["specificVar"], 1e-9)


def test_black_litterman_precision_blend():
    # prior N(0, 0.04); a confident view q=0.02, omega=0.0001 -> posterior pulled toward view
    bl = L.black_litterman(0.0, 0.04, [{"q": 0.02, "omega": 0.0001}])
    assert 0.0 < bl["postMu"] < 0.02 and bl["postMu"] > 0.018   # confident view dominates
    assert bl["postVar"] < 0.04                                 # posterior tighter than prior
    # no views -> posterior == prior
    bl0 = L.black_litterman(0.005, 0.02, [])
    assert approx(bl0["postMu"], 0.005) and approx(bl0["postVar"], 0.02)


def test_entropy_pool_hits_target():
    p = [0.25, 0.25, 0.25, 0.25]
    x = [-0.02, -0.01, 0.01, 0.02]
    ep = L.entropy_pool(p, x, target=0.01)
    assert approx(ep["achieved"], 0.01, 1e-4)        # constraint satisfied
    assert approx(sum(ep["q"]), 1.0, 1e-3)
    assert ep["kl"] >= 0                              # relative entropy non-negative
    # upweights the higher-x scenarios
    assert ep["q"][3] > ep["q"][0]


def test_alert_score_properties():
    base = L.alert_score(0.7, 0.01, 0.05, 5e6, 4e6, True, 1.0)
    assert base > 0
    assert L.alert_score(0.7, 0.02, 0.05, 5e6, 4e6, True, 1.0) > base   # more edge -> higher
    assert L.alert_score(0.7, 0.01, 0.20, 5e6, 4e6, True, 1.0) < base   # more tail risk -> lower
    assert L.alert_score(0.7, 0.01, 0.05, 5e6, 4e6, False, 1.0) == 0.0  # not modellable -> 0
    assert L.alert_score(0.7, 0.01, 0.05, 5e6, 4e6, True, 0.0) == 0.0   # blocked governance -> 0


def test_bs_and_heston_and_merton():
    import math
    bs = L.bs_call(100, 100, 1.0, 0.0, 0.2)
    assert abs(bs - 7.9656) < 0.02, bs                       # known ATM BS value
    # Heston with tiny xi, rho=0, v0=theta=0.04 -> ~ BS(0.2)
    hes = L.heston_call(100, 100, 1.0, 0.0, 0.04, 2.0, 0.04, 0.01, 0.0)
    assert abs(hes - bs) < 0.25, (hes, bs)
    # Merton with lam=0 -> BS
    mer = L.merton_call(100, 100, 1.0, 0.0, 0.2, 0.0, 0.0, 0.0)
    assert abs(mer - bs) < 0.02, (mer, bs)
    # jumps add value (event risk)
    mer_j = L.merton_call(100, 100, 1.0, 0.0, 0.2, 1.0, -0.1, 0.15)
    assert mer_j > bs


def test_kalman_tracks_latent_level():
    import random
    random.seed(71)
    true = []; x = 0.0
    for _ in range(300):
        x += random.gauss(0, 0.01); true.append(x)
    obs = [true[i] + random.gauss(0, 0.05) for i in range(len(true))]
    filt = L.kalman_local_level(obs, q=1e-4, r=2.5e-3)
    err_filt = sum((filt[i] - true[i]) ** 2 for i in range(50, len(true)))
    err_raw = sum((obs[i] - true[i]) ** 2 for i in range(50, len(true)))
    assert err_filt < err_raw                                # filter beats raw observation


def test_hawkes_mv_and_sqrt_impact():
    mu = [0.5, 0.5]; alpha = [[0.0, 0.0], [0.8, 0.0]]; beta = 1.0   # ch0 excites ch1
    base = L.hawkes_mv_intensity(mu, alpha, beta, [], now=10.0)
    exc = L.hawkes_mv_intensity(mu, alpha, beta, [(0, 9.5)], now=10.0)
    assert exc[1] > base[1] and approx(exc[0], base[0])           # ch1 excited by a ch0 event
    assert L.sqrt_impact(0.02, 0.25) > L.sqrt_impact(0.02, 0.04)  # impact rises with participation


def test_resampling_reality_check_spa_rw():
    import random
    random.seed(72)
    n = 200
    good = [0.004 + random.gauss(0, 0.01) for _ in range(n)]   # genuinely positive differential
    noise = [random.gauss(0, 0.01) for _ in range(n)]
    idx = L.stationary_bootstrap_indices(n, 0.1, seed=5)
    assert len(idx) == n and max(idx) < n and min(idx) >= 0
    # a real edge -> low RC/SPA p; pure noise -> high p
    assert L.reality_check([good], B=200) < 0.1
    assert L.reality_check([noise], B=200) > 0.1
    assert L.spa_test([good], B=200) < 0.2
    rw = L.romano_wolf([good, noise], B=200)
    bym = {r["model"]: r for r in rw}
    assert bym[0]["rejected"] is True and bym[1]["rejected"] is False


def test_simm_frtb_pla_stans_cube():
    import random
    # SIMM bucket: K rises with correlation
    assert L.simm_bucket([1.0, 1.0, 1.0], 0.8) > L.simm_bucket([1.0, 1.0, 1.0], 0.1)
    sba = L.frtb_sba([1.0, 0.5], [0.3], 0.1)
    assert sba["high"] >= sba["low"]
    # PLA: identical P&L -> green; reversed -> red
    random.seed(73); a = [random.gauss(0, 0.02) for _ in range(100)]
    assert L.pla_test(a, a)["zone"] == "green"
    assert L.pla_test([-x for x in a], a)["zone"] == "red"
    # STANS ES: negative loss, stressed more severe
    r = [random.gauss(0, 0.02) for _ in range(400)]
    st = L.stans_es(r); assert st["es99_2d"] < 0 and st["stressedES"] <= st["es99_2d"]
    # scenario cube worst-case
    cube = L.scenario_cube({"20d": 0.06})
    assert approx(cube["scanRisk"]["20d"], round(-3 * 0.06 * 1.3, 5))
    assert len(cube["riskArray"]) == 21


def test_entropy_pool_regimes_reweights():
    q = L.entropy_pool_regimes([0.5, 0.5], [-0.02, 0.02], target_mu=0.01)
    assert q is not None and approx(sum(q), 1.0, 1e-3)
    assert q[1] > q[0]    # upweight the higher-drift regime to hit a positive target


if __name__ == "__main__":
    _fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for _f in _fns:
        _f(); print("PASS", _f.__name__)
    print("\nALL %d LINEAGE TESTS PASSED" % len(_fns))
