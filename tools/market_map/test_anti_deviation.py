#!/usr/bin/env python3
"""Regression tests for anti_deviation.py — the post-forecast anti-deviation control layer. Pins the
integrity rules (maturity gating, dependence-discounted n_eff, shrinkage + hard caps) and each of the four
controllers on planted structure. Auto-discovered by run-checks.sh / verify_all.sh."""
import math
import random

import anti_deviation as ad


def test_maturity_gating_no_leakage():
    led = ad.ForecastLedger()
    led.issue("A", origin_ts=10, horizon_h=5, mu_raw=0.0, sigma_raw=1.0, lower=-1.6, upper=1.6)  # matures at 15
    realized = {("A", 10, 5): 0.3}
    # before maturity: nothing matures even though the outcome is "known"
    assert led.mature(now_ts=14, realized=realized) == 0 and led.matured == []
    # outcome unknown past maturity: still no leakage
    assert led.mature(now_ts=99, realized={}) == 0 and led.open and led.matured == []
    # matured only when now >= maturity AND outcome present
    assert led.mature(now_ts=99, realized=realized) == 1 and len(led.matured) == 1
    rec = led.matured[0]
    assert rec["side"] == "inside" and rec["coverageFlag"] == 1 and abs(rec["residual"] - 0.3) < 1e-9


def test_effective_n_discounts_dependence():
    random.seed(1)
    iid = [random.gauss(0, 1) for _ in range(400)]
    ar = [0.0] * 400
    e = 0.0
    for i in range(400):
        e = 0.8 * e + random.gauss(0, 1)
        ar[i] = e
    n_iid = ad.effective_n(iid)
    n_ar = ad.effective_n(ar)
    assert n_iid > 0.7 * len(iid)            # ~iid -> n_eff near n
    assert n_ar < 0.5 * len(ar)              # strong positive autocorrelation -> n_eff sharply discounted
    assert n_ar < n_iid


def test_center_controller_shrinks_and_caps():
    resid = [0.4 + random.gauss(0, 1.0) for _ in range(300)]   # planted +0.4 bias
    b = ad.center_bias(resid, resid_parent=[0.0] * 300, sigma_raw=1.0)
    assert 0.0 < b < 0.4                                       # positive but SHRUNK toward parent 0
    # hard cap at 0.5·sigma: a huge bias is clamped
    big = [5.0] * 200
    assert abs(ad.center_bias(big, sigma_raw=1.0)) <= 0.5 + 1e-9


def test_scale_controller_clips():
    random.seed(2)
    under = [1.5 * random.gauss(0, 1) for _ in range(300)]     # residuals 1.5x the implied sigma
    s = ad.scale_factor(under)
    assert s > 1.0 and s <= ad.SCALE_MAX
    well = [random.gauss(0, 1) for _ in range(300)]
    assert abs(ad.scale_factor(well) - 1.0) < 0.25             # well-scaled -> ~1
    runaway = [20.0 * random.gauss(0, 1) for _ in range(300)]
    assert ad.scale_factor(runaway) == ad.SCALE_MAX            # clipped, never runs away


def test_tail_controller_asymmetric():
    random.seed(3)
    # right-skewed residuals: occasional large POSITIVE jumps -> upper tail fatter than lower
    z = []
    for _ in range(500):
        x = random.gauss(0, 1)
        if random.random() < 0.15:
            x += abs(random.gauss(0, 3))
        z.append(x)
    ql, qu = ad.tail_quantiles(z, alpha=0.10)
    assert ql < 0 < qu and qu > abs(ql)                       # asymmetry preserved (not mirrored)


def test_coverage_controller_adapts():
    a_lo, a_hi = 0.05, 0.05
    # a lower-side miss (y below lower bound) must raise the lower miscoverage parameter
    nlo, nhi = ad.coverage_update(a_lo, a_hi, y=-5.0, lo=-1.6, hi=1.6)
    assert nlo > a_lo and abs(nhi - a_hi) < 0.01
    # an inside point nudges both gently toward target
    nlo2, nhi2 = ad.coverage_update(a_lo, a_hi, y=0.0, lo=-1.6, hi=1.6)
    assert nlo2 != a_lo and nhi2 != a_hi


def test_gate_blocks_thin_buckets():
    assert ad.gate(n_eff_local=20, n_eff_parent=500, isc_delta=10, stable=True) is False   # local too thin
    assert ad.gate(n_eff_local=200, n_eff_parent=10, isc_delta=10, stable=True) is False    # parent too thin
    assert ad.gate(n_eff_local=200, n_eff_parent=500, isc_delta=-1, stable=True) is False    # no benefit
    assert ad.gate(n_eff_local=200, n_eff_parent=500, isc_delta=10, stable=True) is True


def test_end_to_end_improves_interval_score():
    random.seed(5)
    led = ad.ForecastLedger()
    # planted +0.4 bias and 1.4x under-scaled sigma across 240 matured forecasts
    truth = {}
    for t in range(240):
        led.issue("X", t, 5, 0.0, 1.0, -1.645, 1.645)
        truth[("X", t, 5)] = 0.4 + random.gauss(0, 1.4)
    led.mature(now_ts=10_000, realized=truth)
    cut = 170
    fit = ad.fit_controllers(led.matured[:cut], sigma_raw_ref=1.0)
    assert fit["active"] is True and fit["biasAdj"] > 0 and fit["scaleAdj"] > 1.0
    # evaluate corrected vs raw band on HELD-OUT matured points
    raw_s = adj_s = 0.0
    for m in led.matured[cut:]:
        y = m["y"]
        raw = {"active": False}
        rb = ad.apply_controllers(m["muRaw"], m["sigmaRaw"], raw)
        ab = ad.apply_controllers(m["muRaw"], m["sigmaRaw"], fit)
        raw_s += ad.interval_score(y, rb["lower"], rb["upper"])
        adj_s += ad.interval_score(y, ab["lower"], ab["upper"])
    assert adj_s < raw_s, (adj_s, raw_s)                       # corrected band genuinely better out-of-sample


def test_apply_passthrough_when_gated():
    out = ad.apply_controllers(0.0, 2.0, {"active": False})
    assert out["active"] is False and out["biasAdj"] == 0.0 and out["scaleAdj"] == 1.0
    assert out["lower"] < 0 < out["upper"]


if __name__ == "__main__":
    for name in sorted(k for k in dict(globals()) if k.startswith("test_")):
        globals()[name]()
        print("PASS", name)
    print("ALL test_anti_deviation PASS")
