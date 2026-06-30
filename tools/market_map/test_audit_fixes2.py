#!/usr/bin/env python3
"""Regression tests for the second mathematical audit (Mathematical Audit of the MrktPrice Repository Source).
Each test pins the corrected behavior so the fix cannot silently regress. Auto-discovered by run-checks.sh.

Findings covered:
  #1 American/European parity firewall   -> parity.implied_forward style flag; q-override gated on european
  #2 VRP forward consistency             -> risk_neutral.variance_risk_premium threads the same forward
  #3 Intraday tradable rule upside-down  -> intraday_engine.decision uses conservative lower-confidence edge
  #6 BL density negative-mass diagnostic -> risk_neutral.bl_density(with_diag=True) reports negMassShare
  #7 conformal language vs implementation-> intraday_engine.conformal_band uses order-statistic quantiles
  #5 HARQ daily-square honesty           -> harq_regime output carries realizedMeasure='daily_square_proxy'
  #4 Driscoll-Kraay pseudo-time honesty  -> drift_calib3 tidxKind/dkLabel flag; real dates supported
"""
import math
import intraday_engine as ie
import risk_neutral as rn
import parity as par
import drift_calib3 as dc
import harq_regime as hq


def test_intraday_no_edge_counterexample():
    # audit counterexample: zero point forecast, symmetric band straddling current price, cost 0.001
    hi = [0.0, 0.0, 0.02]; lo = [0.0, 0.0, -0.02]
    d = ie.decision(0.0, hi, lo, h_idx=2, cost=0.001, G=1.0)
    assert d["tradable"] is False, d                  # uncertainty width must NOT manufacture a trade
    assert d["optLong"] > 0                            # the OLD optimistic score would have fired (bug proof)
    # genuine long edge: even the lower bound clears current + cost
    hi2 = [0, 0, 0.03]; lo2 = [0, 0, 0.01]
    d2 = ie.decision(0.0, hi2, lo2, h_idx=2, cost=0.001, G=1.0)
    assert d2["tradable"] and d2["side"] == "long" and abs(d2["edge"] - 0.009) < 1e-9, d2
    # genuine short edge: even the upper bound is below current - cost
    hi3 = [0, 0, -0.01]; lo3 = [0, 0, -0.03]
    d3 = ie.decision(0.0, hi3, lo3, h_idx=2, cost=0.001, G=1.0)
    assert d3["tradable"] and d3["side"] == "short", d3
    # hard regime gate still vetoes
    assert ie.decision(0.0, hi2, lo2, h_idx=2, cost=0.001, G=0.0)["tradable"] is False


def _toy_chain(spot=100.0):
    # symmetric strikes with simple monotone marks so parity/VRP run
    chain = []
    for K in (80, 90, 100, 110, 120):
        c = max(spot - K, 0) + 3.0; p = max(K - spot, 0) + 3.0
        chain.append({"strike": K, "type": "C", "mark": c})
        chain.append({"strike": K, "type": "P", "mark": p})
    return chain


def test_parity_exercise_firewall():
    chain = _toy_chain()
    am = par.implied_forward(chain, 100.0, 0.25, 0.04, style="american")
    eu = par.implied_forward(chain, 100.0, 0.25, 0.04, style="european")
    assert am and am["europeanValid"] is False and am["impliedDivYieldValid"] is False and am["style"] == "american"
    assert eu and eu["europeanValid"] is True and eu["impliedDivYieldValid"] is True
    # default style is american (the OCC single-name default) — must not silently claim European validity
    dft = par.implied_forward(chain, 100.0, 0.25, 0.04)
    assert dft["europeanValid"] is False


def test_vrp_forward_consistency():
    chain = []
    for K in (80, 90, 100, 110, 120):
        chain.append({"strike": K, "type": "C", "mark": max(100 - K, 0) + 2.0})
        chain.append({"strike": K, "type": "P", "mark": max(K - 100, 0) + 2.0})
    F = 101.0
    mf_with_F = rn.model_free_iv(chain, 100.0, 0.25, 0.04, forward=F)
    vrp = rn.variance_risk_premium(chain, 100.0, 0.25, 0.04, 0.04, forward=F)
    if mf_with_F and vrp:
        # the implied variance inside VRP must equal the standalone mf computed with the SAME forward
        assert abs(vrp["impliedVar"] - round(mf_with_F["mfImpliedVar"], 6)) < 1e-9, (vrp, mf_with_F)
    # and passing no forward differs from passing a non-spot forward (proves it is actually threaded)
    mf_spot = rn.model_free_iv(chain, 100.0, 0.25, 0.04)
    if mf_with_F and mf_spot:
        assert mf_with_F["F"] != mf_spot["F"]


def test_bl_negative_mass_diagnostic():
    conv = [(90, 12.0), (95, 8.0), (100, 4.5), (105, 2.0), (110, 0.7)]   # convex => arbitrage-consistent
    d = rn.bl_density(conv, 0.5, 0.04, with_diag=True)
    assert d["nConvexityViolations"] == 0 and d["negMassShare"] == 0.0 and d["arbConsistent"] is True
    bad = [(90, 12.0), (95, 4.0), (100, 8.0), (105, 2.0), (110, 0.7)]    # butterfly violation
    d2 = rn.bl_density(bad, 0.5, 0.04, with_diag=True)
    assert d2["nConvexityViolations"] >= 1 and d2["negMassShare"] > 0 and d2["arbConsistent"] is False
    # backward-compatible default still returns the density list
    assert isinstance(rn.bl_density(conv, 0.5, 0.04), list)


def test_conformal_order_statistic():
    res = {h: list(range(-10, 11)) for h in range(3)}   # 21 residuals per horizon
    lo, hi = ie.conformal_band([0.0, 0.0, 0.0], res, alpha=0.90)
    # finite-sample order statistic: upper ceil(0.95*22)=21 -> max resid 10 ; lower floor(0.05*22)=1 -> -10
    assert hi[0] == 10 and lo[0] == -10, (lo, hi)


def test_harq_realized_measure_label():
    import random
    random.seed(1)
    closes = [100.0]
    for _ in range(220):
        closes.append(closes[-1] * math.exp(random.gauss(0, 0.012)))
    out = hq.harq_regime_forecast(closes)
    assert out and out.get("realizedMeasure") == "daily_square_proxy" and out.get("harqFaithful") is False


def test_dk_tidx_honesty():
    import random
    random.seed(2)
    def series(n):
        c = [100.0]
        for _ in range(n):
            c.append(c[-1] * math.exp(random.gauss(0, 0.012)))
        return c
    names = [series(120), series(140), series(110)]
    res = dc.calibrate3(names)                                   # no dates -> pseudo-panel HAC
    assert res.get("tidxKind") == "bars_from_end" and "pseudo-panel HAC" in res.get("dkLabel", "")
    # supplying shared ordinal dates flips it to genuine calendar-aligned DK
    dates = [list(range(len(s))) for s in names]
    res2 = dc.calibrate3(names, dates_by_name=dates)
    assert res2.get("tidxKind") == "calendar_date" and "calendar-aligned" in res2.get("dkLabel", "")


if __name__ == "__main__":
    for name in sorted(k for k in dict(globals()) if k.startswith("test_")):
        globals()[name]()
        print("PASS", name)
    print("ALL test_audit_fixes2 PASS")
