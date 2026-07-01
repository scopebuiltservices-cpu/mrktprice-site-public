#!/usr/bin/env python3
"""validation_scorecard.py — the live validation reporting pack (pure stdlib).

Wires the Validation Report's evaluation panel to the REAL matured-forecast ledger (maturity_protocol
or anti_deviation.ForecastLedger). Given matured coverage records it emits, per horizon and overall:
empirical coverage + Wilson CI, average width, mean interval (Winkler) score, STRATIFIED coverage
(vol regime / time-of-day / event regime / up-vs-down) with miscalibration flags, and the tail-noise /
sample-size stability panel. This is the "stratified coverage wired into the live scorecard" step —
coverage_strata + tail_stability now consume the production ledger, not just offline synthetic data.

REUSES coverage_strata.stratified_coverage, tail_stability.tail_panel, anti_deviation.interval_score.
Verified in test_validation_scorecard.py against a planted miscalibrated stratum + an unstable tail.
"""
from __future__ import annotations

from coverage_strata import stratified_coverage, wilson_interval
from tail_stability import tail_panel
from anti_deviation import interval_score


def _vol_bucket(sigma, edges):
    """Label a sigma into low/mid/high by fixed percentile-style edges (caller supplies edges)."""
    if sigma is None or sigma != sigma or not edges:
        return None
    lo, hi = edges
    return "low" if sigma < lo else ("high" if sigma > hi else "mid")


def tag_record(rec, vol_edges=None, tod_fn=None):
    """Turn a matured ledger record into a coverage_strata record: covered/horizon/sign + strata dims.
    volRegime from sigma bucket; tod from a caller-supplied issueT->bucket fn; event from meta; sign
    from the residual. Anything unknown is left absent (that dimension is skipped, never guessed)."""
    out = {"covered": bool(rec.get("covered")), "horizon": rec.get("H"),
           "sign": rec.get("sign") or ("up" if (rec.get("residual", 0) or 0) >= 0 else "down")}
    vb = _vol_bucket(rec.get("sigma"), vol_edges)
    if vb is not None:
        out["volRegime"] = vb
    meta = rec.get("meta") or {}
    if "volRegime" in meta:
        out["volRegime"] = meta["volRegime"]
    if "event" in meta:
        out["event"] = meta["event"]
    if tod_fn is not None and rec.get("issueT") is not None:
        try:
            out["tod"] = tod_fn(rec["issueT"])
        except Exception:
            pass
    elif "tod" in meta:
        out["tod"] = meta["tod"]
    return out


def _band_cell(recs, nominal, alpha):
    """Coverage + Wilson CI + avg width + mean interval score for a set of matured records that carry
    a band (lower/upper) and outcome y."""
    n = len(recs)
    if n == 0:
        return {"n": 0}
    k = sum(1 for r in recs if r.get("covered"))
    phat, lo, hi = wilson_interval(k, n)
    widths, iscs = [], []
    for r in recs:
        L, U, y = r.get("lower"), r.get("upper"), r.get("y")
        if L is not None and U is not None and y is not None:
            widths.append(U - L)
            iscs.append(interval_score(y, L, U, alpha))
    cell = {"n": n, "coverage": round(k / n, 4), "wilsonLo": round(lo, 4), "wilsonHi": round(hi, 4),
            "miscalibrated": bool(nominal < lo or nominal > hi)}
    if widths:
        cell["avgWidth"] = round(sum(widths) / len(widths), 6)
        cell["meanIntervalScore"] = round(sum(iscs) / len(iscs), 6)
    return cell


def scorecard(records, nominal: float = 0.90, vol_edges=None, tod_fn=None,
              embargo_overlap=None, stable_tol: float = 0.5) -> dict:
    """Build the full validation pack from matured ledger records.

    records: matured dicts carrying at least covered/H/sigma/residual and (for width/IS) lower/upper/y.
    nominal: target coverage. vol_edges: (lo,hi) sigma cut points for the vol-regime stratum. tod_fn:
    issueT->time-of-day bucket. embargo_overlap: label overlap H for the tail-stability effective N."""
    alpha = round(1.0 - nominal, 4)
    out = {"nominal": nominal, "alpha": alpha, "nTotal": len(records)}

    # per-horizon band metrics (coverage + Wilson + width + interval score)
    byh = {}
    for r in records:
        byh.setdefault(r.get("H"), []).append(r)
    out["byHorizon"] = {str(h): _band_cell(v, nominal, alpha)
                        for h, v in sorted(byh.items(), key=lambda kv: (kv[0] is None, kv[0]))}
    out["marginal"] = _band_cell(records, nominal, alpha)

    # stratified coverage (vol regime / tod / event / sign) with miscalibration flags
    strata_recs = [tag_record(r, vol_edges=vol_edges, tod_fn=tod_fn) for r in records]
    out["stratified"] = stratified_coverage(strata_recs, nominal=nominal)

    # tail-noise / sample-size stability, per horizon, on the studentized residuals
    tails = {}
    for h, v in byh.items():
        stud = [r["stud"] for r in v if r.get("stud") is not None]
        if len(stud) >= 5:
            ov = embargo_overlap if embargo_overlap is not None else (h or 1)
            tails[str(h)] = tail_panel(stud, alpha=alpha / 2.0, overlap=ov, stable_tol=stable_tol)
    out["tailStability"] = tails

    out["flags"] = list(out["stratified"].get("flags", []))
    for h, tp in tails.items():
        if not tp.get("stable", True):
            out["flags"].append({"kind": "tailUnstable", "horizon": h, "reason": tp.get("reason")})
    out["ok"] = (len(out["flags"]) == 0)
    return out
