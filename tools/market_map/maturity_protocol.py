#!/usr/bin/env python3
"""maturity_protocol.py — the leakage-free maturity + purge/embargo update state machine (pure stdlib).

Implements the Validation Report's horizon-H calibration lifecycle flowchart as an explicit, testable
state machine. Three DISTINCT timestamps are tracked per forecast (reviewers routinely miss that these
differ):

    issue_t       forecast is produced using info available at issue_t only (then FROZEN)
    maturity_t    = issue_t + H     — the H-step outcome is fully observed; the residual can be computed
    inclusion_t   = maturity_t + E   — earliest issue time a NEW forecast may USE this residual (E = embargo)

The residual of a forecast issued at t may enter the horizon-H calibration pool ONLY at inclusion_t, and
that pool may be consumed ONLY by forecasts whose issue time >= inclusion_t ("quantiles update for future
forecasts only"). Overlapping H-step labels are handled by the embargo E (default E = H, i.e. "purge or
embargo at least H observations around each boundary"), which guarantees a matured residual's whole label
window closes at least E steps before any forecast that consumes it.

Matured records are emitted in the exact shape coverage_strata / validation_scorecard consume (covered,
horizon, sign, plus any issue-time meta). Verified leakage-free in test_maturity_protocol.py.
"""
from __future__ import annotations


class MaturityProtocol:
    def __init__(self, embargo=None):
        """embargo E in the same time units as issue times. None -> per-record E = H (recommended:
        at least H, the report's rule for overlapping labels)."""
        self.embargo = embargo
        self._open = {}       # fid -> forecast dict (issued, not yet matured)
        self._matured = []    # matured records (residual known, carries inclusion_t)

    def issue(self, fid, issue_t, H, mu, sigma, lower, upper, meta=None):
        """Register a frozen forecast. lower/upper are the predictive band in the SAME space as the
        realized outcome that will be supplied to observe()."""
        E = self.embargo if self.embargo is not None else H
        self._open[fid] = {"fid": fid, "issueT": issue_t, "H": H, "maturityT": issue_t + H,
                           "inclusionT": issue_t + H + E, "mu": mu, "sigma": sigma,
                           "lower": lower, "upper": upper, "meta": dict(meta or {})}
        return self._open[fid]

    def observe(self, now_t, realized_by_fid):
        """Advance the clock to now_t. Any OPEN forecast whose maturity_t <= now_t AND whose outcome is
        known matures: its residual is computed and it moves to the matured pool (still gated by
        inclusion_t before it can be USED). Returns the list of records that matured on this call."""
        matured_now = []
        for fid in list(self._open):
            f = self._open[fid]
            if now_t >= f["maturityT"] and fid in realized_by_fid:
                y = float(realized_by_fid[fid])
                sig = f["sigma"]
                resid = y - f["mu"]
                rec = {"fid": fid, "issueT": f["issueT"], "H": f["H"], "maturityT": f["maturityT"],
                       "inclusionT": f["inclusionT"], "y": y, "mu": f["mu"], "sigma": sig,
                       "residual": resid, "stud": (resid / sig if (sig and sig == sig and sig > 0) else None),
                       "covered": bool(f["lower"] <= y <= f["upper"]),
                       "sign": ("up" if resid >= 0 else "down"), "meta": f["meta"]}
                self._matured.append(rec)
                matured_now.append(rec)
                del self._open[fid]
        return matured_now

    def calibration_pool(self, as_of_issue_t, horizon=None, window=None):
        """Residuals usable by a NEW forecast issued at as_of_issue_t: matured AND past embargo
        (inclusion_t <= as_of_issue_t) AND — the purge — outcome known strictly before the new forecast
        (maturity_t <= as_of_issue_t, implied by inclusion_t with E>=0). Optionally filter to a horizon
        and trim to the most recent `window` residuals."""
        pool = [r for r in self._matured
                if r["inclusionT"] <= as_of_issue_t and (horizon is None or r["H"] == horizon)]
        pool.sort(key=lambda r: r["inclusionT"])
        if window is not None and len(pool) > window:
            pool = pool[-window:]
        return pool

    def matured_records(self, horizon=None):
        """All matured coverage records (for the scorecard). Optionally filter by horizon."""
        return [r for r in self._matured if (horizon is None or r["H"] == horizon)]

    def leakage_ok(self):
        """Invariant self-check: every matured residual's outcome is known before its inclusion time
        (inclusion_t >= maturity_t) — i.e. no residual can be USED before its outcome exists."""
        return all(r["inclusionT"] >= r["maturityT"] for r in self._matured)

    def open_count(self):
        return len(self._open)
