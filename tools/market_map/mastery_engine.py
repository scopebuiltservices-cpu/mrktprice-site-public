"""mastery_engine.py — evidence-based SIGNAL-MASTERY gate (adapted from the mastery-evaluation framework:
Bloom/Dreyfus/mastery-learning/IRT). Decides whether a forecast or strategy is NOVICE / PROFICIENT /
MASTERY (deployable) using an analytic-weighted composite, must-pass critical components, a two-confirmation
rule, and IRT-style confidence bands — replacing single-threshold "got lucky once" promotion. Pure stdlib;
verified; 1:1 JS port. Research only, not advice.

Component scores are normalized to [0,1] (domain-agnostic, like the report's template). A practical
market mapping: concepts->data sufficiency, procedure->OOS skill/IC, reasoning->calibration coverage,
transfer->cross-regime/OOS DSR, self-monitoring->stability(low drift). `criticals` are the must-pass set.

THREE-GATE THRESHOLDS (report defaults, on a 0-100 composite):
  novice     : overall < 70, OR any critical < 60, OR > maxMiscon stable misconceptions
  proficient : 70 <= overall < 85 AND all criticals >= 60
  mastery    : overall >= 85 AND all criticals >= 80 AND no critical error AND TWO-CONFIRMATION passes
"""
import math

__all__ = ["composite", "confidence_band", "two_confirmation", "classify", "reclassify"]

DEFAULT_WEIGHTS = {"concepts": 0.20, "procedure": 0.25, "reasoning": 0.20, "transfer": 0.25, "selfmon": 0.10}


def composite(components, weights=None):
    """Analytic-weighted composite in [0,100]. components: {name: score in [0,1]}; weights renormalized
    over the components actually present."""
    w = dict(weights or DEFAULT_WEIGHTS)
    keys = [k for k in w if k in components and components[k] is not None]
    if not keys:
        return 0.0
    tw = sum(w[k] for k in keys)
    if tw <= 0:
        return 0.0
    return 100.0 * sum((w[k] / tw) * max(0.0, min(1.0, components[k])) for k in keys)


def confidence_band(n, se=None, n_strong=500, n_moderate=120):
    """IRT/evidence band. 'strong' if many matured samples (and tight SE), 'moderate' if some,
    'insufficient' otherwise. se (optional) in score units widens the bar."""
    if n is None or n < 30:
        return "insufficient"
    wide = (se is not None and se > 0.15)
    if n >= n_strong and not wide:
        return "strong"
    if n >= n_moderate:
        return "moderate" if not wide else "insufficient"
    return "moderate" if n >= 60 else "insufficient"


def two_confirmation(initial_pass, delayed_pass):
    """Mastery requires the criterion met on an INITIAL authentic (OOS) window AND a DELAYED/parallel one
    (purged) — guards against luck, leakage, coaching contamination, or a good day."""
    return bool(initial_pass) and bool(delayed_pass)


def classify(components, criticals=None, weights=None, critical_error=False,
             n_misconceptions=0, max_miscon=2, initial_pass=True, delayed_pass=True,
             n=None, se=None, crit_floor_prof=60.0, crit_floor_mast=80.0,
             prof_overall=70.0, mast_overall=85.0):
    """Return the mastery classification with the explicit reason it landed there.
    `criticals`: {name: score0..1} must-pass components (e.g. no-leak, coverage, DSR, drift). A critical
    below its floor (or a hard critical_error) blocks the higher tier regardless of the composite."""
    crit = criticals or {}
    overall = composite(components, weights)
    crit100 = {k: 100.0 * max(0.0, min(1.0, v)) for k, v in crit.items()}
    min_crit = min(crit100.values()) if crit100 else 100.0
    blocked = []
    if critical_error:
        blocked.append("critical_error")
    for k, v in crit100.items():
        if v < crit_floor_prof:
            blocked.append("critical:%s<%.0f" % (k, crit_floor_prof))
    # NOVICE conditions
    if overall < prof_overall or min_crit < crit_floor_prof or n_misconceptions > max_miscon:
        tier = "novice"
    elif overall >= mast_overall and min_crit >= crit_floor_mast and not critical_error \
            and two_confirmation(initial_pass, delayed_pass):
        tier = "mastery"
    else:
        tier = "proficient"
    # explain why mastery was NOT reached (if proficient/novice but composite high)
    why = []
    if tier != "mastery":
        if overall < mast_overall:
            why.append("overall %.0f<85" % overall)
        if min_crit < crit_floor_mast:
            why.append("a critical<80")
        if critical_error:
            why.append("critical error")
        if not two_confirmation(initial_pass, delayed_pass):
            why.append("needs delayed re-confirm")
    return {"tier": tier, "overall": round(overall, 1), "minCritical": round(min_crit, 1),
            "band": confidence_band(n, se), "blockedBy": blocked, "whyNotMastery": why,
            "deployable": tier == "mastery"}


def reclassify(history, maintain=80.0):
    """Downward reclassification: demote if the TWO most recent delayed checks both regressed below the
    maintenance threshold. history: list of delayed composite scores (newest last)."""
    if len(history) < 2:
        return False
    return history[-1] < maintain and history[-2] < maintain
