"""volatility_arbiter.py — reliability-weighted volatility blend.

Implements the "Scale upgrade" from the Production-Ready Integration report: instead of a single
sqrt-of-time or single-estimator sigma, produce ONE horizon sigma_H by blending physical variance
components (HV_H, EWMA/GARCH, HARQ, realized-vol) in VARIANCE space, weighted by base priority x
availability x a [0,1] reliability score, then optionally shrink toward a variance-ratio overlay
(diagnostic, not oracle), then ADD scheduled-event and jump/EVT tail variance, and take a single
square root at the end. Emits named weights + a first-class reliability score so downstream
calibration and the UI can see *why* the scale is what it is.

    w_i          = base_weight_i * availability_i * clip(reliability_i, 0, 1),  normalized
    sigma2_phys  = sum_i w_i * sigma_i^2
    sigma2_blend = (1 - lambda_VR) * sigma2_phys + lambda_VR * sigma_VR^2      (overlay, lambda in [0,1])
    sigma2_total = sigma2_blend + sigma_event^2 + sigma_jump^2
    sigma_H      = clip(sqrt(sigma2_total), floor, cap)

Pure-stdlib port of the report's numpy reference (this repo's engines are keyless / numpy-free).
Never averages sigmas directly — averaging standard deviations understates blended variance.
"""
import math

VERSION = "vol_arbiter_v1"


def component(name, sigma, reliability, base_weight=1.0, available=True):
    """A physical volatility estimate + its credibility. sigma and reliability are per-horizon."""
    return {"name": str(name), "sigma": float(sigma), "reliability": float(reliability),
            "base_weight": float(base_weight), "available": bool(available)}


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def vr_lambda(vr, n_eff, min_n=60, kmax=0.5):
    """Credibility in [0, kmax] of a variance-ratio overlay (the report treats VR as a DIAGNOSTIC,
    not an oracle). Rises with (overlap-aware) sample size and engages more as VR departs from the
    linear-variance null of 1. Returns 0 when thin or when VR ~ 1 (nothing to correct)."""
    if vr is None or n_eff is None or n_eff < min_n:
        return 0.0
    samp = _clip((n_eff - min_n) / (3.0 * min_n), 0.0, 1.0)   # 0 at min_n, 1 at 4*min_n
    dep = _clip(abs(vr - 1.0) / 0.5, 0.0, 1.0)                # |VR-1| >= 0.5 -> full departure
    return round(kmax * samp * dep, 6)


def blend(physical, sigma_vr=None, vr_reliability=0.0, event_sigma=0.0, jump_sigma=0.0,
          floor=1e-6, cap=10.0):
    """Blend variance components conservatively into one sigma_H. `physical` is a list of component()
    dicts. Returns {sigma, sigma2, weights, reliability, components, version}."""
    usable = [c for c in physical if c.get("available", True) and c.get("sigma", 0.0) > 0.0]
    if not usable:
        raise ValueError("no usable physical volatility components")

    raw = [max(c.get("base_weight", 1.0), 0.0) * _clip(c.get("reliability", 0.0), 0.0, 1.0)
           for c in usable]
    tot = sum(raw)
    if tot <= 0.0:                       # all-zero credibility -> fall back to equal weights
        raw = [1.0] * len(usable); tot = float(len(usable))
    weights = [r / tot for r in raw]

    sigma2 = sum(w * (max(c["sigma"], 1e-12) ** 2) for w, c in zip(weights, usable))
    out_weights = {c["name"]: round(w, 6) for w, c in zip(weights, usable)}

    if sigma_vr is not None and vr_reliability and vr_reliability > 0.0:
        lam = _clip(float(vr_reliability), 0.0, 1.0)
        sigma2 = (1.0 - lam) * sigma2 + lam * (max(float(sigma_vr), floor) ** 2)
        out_weights["vr_overlay"] = round(lam, 6)

    ev = max(float(event_sigma), 0.0)
    jp = max(float(jump_sigma), 0.0)
    sigma2_total = sigma2 + ev * ev + jp * jp
    sigma = min(max(math.sqrt(sigma2_total), floor), cap)

    mean_rel = sum(w * c.get("reliability", 0.0) for w, c in zip(weights, usable))
    comps = {c["name"]: c["sigma"] for c in usable}
    comps["event_sigma"] = ev
    comps["jump_sigma"] = jp
    return {"sigma": sigma, "sigma2": sigma2_total, "weights": out_weights,
            "reliability": round(mean_rel, 6), "components": comps, "version": VERSION}
