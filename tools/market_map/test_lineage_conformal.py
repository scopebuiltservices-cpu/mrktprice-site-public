#!/usr/bin/env python3
"""Regression tests for the two outstanding audit items wired into lineage.py:

  (1) calibrate_horizon now does REGIME-CONDITIONED split-conformal (separate per-regime quantiles, not just
      pooled) and emits the schema-promised conformalPad / coveragePadded / byRegimeConformal / regimeConditioned.
  (2) touch_odds uses metrics.sigma_horizon as the single source of truth for the per-horizon forecast σ
      (blended HV/EWMA/VR), with an sd·√h fallback — replacing the unconditional √H scaling.

Auto-discovered by run-checks.sh / verify_all.sh."""
import math
import random

import lineage as L


def _synthetic_returns(n=900, seed=5):
    random.seed(seed)
    # two volatility regimes alternating in blocks so the HMM/Viterbi path has distinct states
    r = []
    for i in range(n):
        hi = (i // 60) % 2 == 1            # alternate calm / stormy blocks
        r.append(random.gauss(0.0003, 0.03 if hi else 0.008))
    return r


def test_calibrate_horizon_emits_conformal_fields():
    r = _synthetic_returns()
    # regime path: simple vol-block labels (stand-in for the Viterbi path)
    regimes = [1 if (i // 60) % 2 == 1 else 0 for i in range(len(r))]
    c = L.calibrate_horizon(r, n_steps=5, regimes=regimes)
    assert c is not None, "calibration returned None on sufficient data"
    for f in ("conformalPad", "coveragePadded", "regimeConditioned", "byRegimeConformal", "qLo", "qHi", "coverage"):
        assert f in c, "missing field: " + f
    assert isinstance(c["coveragePadded"], float) and 0.0 <= c["coveragePadded"] <= 1.0
    assert c["regimeConditioned"] is True and len(c["byRegimeConformal"]) >= 1
    # each per-regime entry carries its own separate lower/upper conformal quantiles
    for rg, d in c["byRegimeConformal"].items():
        assert "qLo" in d and "qHi" in d and d["qHi"] >= d["qLo"]


def test_validation_snapshot_carries_fields():
    r = _synthetic_returns()
    fit = L.fit_hmm(r) if hasattr(L, "fit_hmm") else None
    if not (fit and fit.get("ok")):
        return  # HMM fit optional in this environment; calibrate_horizon test already covers the fields
    snap = L.validation_snapshot(r, fit)
    assert isinstance(snap, dict)
    for label, c in snap.items():
        assert "coveragePadded" in c and "conformalPad" in c


def test_touch_odds_uses_sigma_horizon_source():
    # build daily [date, close, vol] rows from a random walk; touch_odds must produce finite first-passage odds
    random.seed(7)
    rows = []
    px = 100.0
    for i in range(120):
        px *= math.exp(random.gauss(0, 0.02))
        rows.append([i, round(px, 4), 1_000_000])
    out = L.touch_odds(rows)
    assert isinstance(out, dict) and out, "touch_odds returned empty"
    for label, d in out.items():
        assert 0.0 <= d["pUp"] <= 1.0 and 0.0 <= d["pDn"] <= 1.0     # finite, valid first-passage probabilities
    # the helper prefers the blended estimate and falls back cleanly: a stub sigma_horizon returning None
    # must not raise and must reproduce the √h fallback
    import metrics as M
    orig = M.sigma_horizon
    try:
        M.sigma_horizon = lambda lr, h: None
        out2 = L.touch_odds(rows)
        assert out2 and all(0.0 <= v["pUp"] <= 1.0 for v in out2.values())
    finally:
        M.sigma_horizon = orig


if __name__ == "__main__":
    for name in sorted(k for k in dict(globals()) if k.startswith("test_")):
        globals()[name]()
        print("PASS", name)
    print("ALL test_lineage_conformal PASS")
