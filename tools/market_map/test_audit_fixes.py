#!/usr/bin/env python3
"""Regression tests for the external-audit fixes (Audit of the MrktPrice Code and Equations + the rolling-HV
/ conformal design note). Each test pins the exact behavior the audit asked for so the fix can't silently
regress. Auto-discovered by tools/run-checks.sh / verify_all.sh.

Covered:
  - pooled_rigor.spa: Hansen consistent recentering (no `* A * 0`); strongly-negative nuisance recenters to 0.
  - metrics.variance_ratio_stat: Lo-MacKinlay heteroskedasticity-robust VR TEST (z + p), not a raw ratio.
  - factor_eval.estimate_sr_trials_std + composite_gate: DSR trial-Sharpe dispersion from the ledger, not 1.0.
  - rate_curve.bootstrap_zero / ZeroCurve: par-yield -> zero/discount bootstrap (not log(1+par) on a par yield).
  - rate_real: HAC (Newey-West) t-stats; honest level/slope/curvature proxy name (not 'Diebold-Li').
  - metrics.sigma_horizon / hv_term_structure / conformal_tails: horizon scale + SEPARATE asymmetric tails.
"""
import math
import random

import metrics
import pooled_rigor
import factor_eval
import composite_gate
import rate_curve
import rate_real


def _closes_from_rets(rets, p0=100.0):
    c = [p0]
    for x in rets:
        c.append(c[-1] * math.exp(x))
    return c


def test_spa_consistent_recentering():
    # K=2 differential-return columns: one genuine beater (mean>0), one strongly-negative nuisance.
    T = 80
    D = [[0.05 + 0.01 * math.sin(t), -0.5 + 0.01 * math.cos(t)] for t in range(T)]
    out = pooled_rigor.spa(D, B=300)
    assert out.get("p") is not None and 0.0 < out["p"] <= 1.0
    # the beater drives the max studentized stat; SPA should find significance (small p)
    assert out["p"] < 0.20, out
    # and the source no longer contains the comedy `* A * 0`
    import inspect
    src = inspect.getsource(pooled_rigor.spa)
    assert "* 0" not in src and "A = 1.0 / 4.0" not in src, "spurious recentering term still present"


def test_variance_ratio_stat_robust():
    random.seed(7)
    rw = [100.0]
    for _ in range(600):
        rw.append(rw[-1] * math.exp(random.gauss(0, 0.01)))
    s = metrics.variance_ratio_stat(rw, q=5)
    assert s and s["z"] is not None and abs(s["vr"] - 1.0) < 0.35  # random walk -> VR ~ 1
    assert abs(s["z"]) < 3.0 and 0.0 <= s["p"] <= 1.0              # usually fails to reject H0
    # positively-autocorrelated (trending) series -> VR > 1 and a large robust z
    tr = [100.0]; mom = 0.0
    for _ in range(600):
        mom = 0.6 * mom + random.gauss(0, 0.01)
        tr.append(tr[-1] * math.exp(mom * 0.3 + random.gauss(0, 0.002)))
    st = metrics.variance_ratio_stat(tr, q=5)
    assert st and st["vr"] > 1.0 and abs(st["z"]) > 2.0, st
    # the raw heuristic still exists but is now labeled as such (no test stat)
    assert metrics.variance_ratio(rw, q=5) is not None


def test_dsr_trial_dispersion():
    a = [0.01, 0.02, -0.01, 0.03, 0.0]
    assert (factor_eval.estimate_sr_trials_std([a, a]) or 0.0) < 1e-9   # identical trials -> ~0 dispersion
    random.seed(3)
    series = [[random.gauss(mu, 0.02) for _ in range(50)] for mu in (0.0, 0.005, 0.01, -0.004, 0.008)]
    sd = factor_eval.estimate_sr_trials_std(series)
    assert sd is not None and sd > 0 and abs(sd - 1.0) > 1e-6        # measured, not the hard-coded 1.0
    # the gate now consumes the estimate and surfaces it
    ic_hist = {"f%d" % i: series[i] for i in range(len(series))}
    weights = {k: 1.0 / len(ic_hist) for k in ic_hist}
    g = composite_gate.gate(ic_hist, weights, horizon=5, n_trials=len(ic_hist))
    assert "srTrialsStd" in g and g["srTrialsStd"] is not None


def test_zero_discount_curve():
    par = [(1 / 12, 0.0445), (0.25, 0.0440), (0.5, 0.0430), (1, 0.0410), (2, 0.0395),
           (3, 0.0390), (5, 0.0395), (7, 0.0405), (10, 0.0420)]
    z = rate_curve.ZeroCurve(rate_curve.bootstrap_zero(par))
    dfs = [z.df(T) for T in (0.5, 1, 2, 5, 10)]
    assert all(0 < d <= 1 for d in dfs) and all(dfs[i] > dfs[i + 1] for i in range(len(dfs) - 1))
    assert abs(z.df(4.0) - math.exp(-z.rate_for(4.0) * 4.0)) < 1e-12   # df <-> zero self-consistency
    # zero rate differs from the OLD naive log(1+par) on the upward-sloping long end
    c = rate_curve.Curve(par)
    assert abs(c.rate_for(10) - c.par_rate_approx(10)) > 1e-4


def test_rate_real_hac_and_honest_name():
    # honest proxy name present; Diebold-Li claim removed from the active docstring
    assert hasattr(rate_real, "real_curve_proxy_lsc")
    d = rate_real.real_curve_proxy_lsc(0.02, 0.025, 0.03)
    assert abs(d["L"] - 0.025) < 1e-9 and abs(d["S"] - 0.01) < 1e-9
    assert "Diebold" not in (rate_real.real_curve_proxy_lsc.__doc__ or "")
    # HAC duration betas run and return finite t-stats on serially-correlated data
    random.seed(11)
    n = 200
    rmkt = [random.gauss(0, 0.01) for _ in range(n)]
    dL = [random.gauss(0, 0.001) for _ in range(n)]
    dS = [random.gauss(0, 0.001) for _ in range(n)]
    dC = [random.gauss(0, 0.001) for _ in range(n)]
    rets = [1.1 * rmkt[i] - 2.0 * dL[i] + random.gauss(0, 0.005) for i in range(n)]
    out = rate_real.duration_betas(rets, rmkt, dL, dS, dC)
    assert out and all(out[k] == out[k] for k in out)   # no NaNs
    assert abs(out["bMKT"] - 1.1) < 0.4                  # recovers the planted market beta


def test_sigma_horizon_and_asymmetric_conformal():
    random.seed(5)
    r = [random.gauss(0, 0.01) for _ in range(800)]
    hv = metrics.hv_term_structure(r, [1, 5, 20])
    assert 5 in hv and 1 in hv and 0.8 < hv[5] / (hv[1] * math.sqrt(5)) < 1.25
    s = metrics.sigma_horizon(r, 5)
    assert s is not None and s > 0
    # left-skewed residuals -> lower tail FATTER than upper (asymmetry preserved, not mirrored)
    random.seed(9)
    res = []
    for _ in range(500):
        x = random.gauss(0, 1)
        if random.random() < 0.15:
            x -= abs(random.gauss(0, 3))
        res.append(x)
    ql, qu = metrics.conformal_tails(res, alpha=0.10)
    assert ql < 0 < qu and abs(ql) > qu
    band = metrics.conformal_band(100.0, 2.0, ql, qu)
    assert band["lower"] < 100 < band["upper"] and (100 - band["lower"]) > (band["upper"] - 100)


if __name__ == "__main__":
    for name in sorted(k for k in dict(globals()) if k.startswith("test_")):
        globals()[name]()
        print("PASS", name)
    print("ALL test_audit_fixes PASS")
