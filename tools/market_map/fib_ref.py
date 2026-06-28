#!/usr/bin/env python3
"""
fib_ref.py — pure-stdlib Python REFERENCE for the multi-horizon (Fibonacci/cadence) projection +
forecast-accuracy system, Phase 1-2. Verified-engine pattern: this is the authoritative reference;
a TS/JS port (Phase 5) will be locked to the committed golden fixture tools/fib_golden.json, and a
Draft-2020-12 contract lives at schemas/fib_forecast.schema.json.

Design decisions baked in (per the review of the research plan):
  * Horizons are a SELECTABLE spacing, not a predictive law. Presets: cadence (default), fib, powers.
    A horizon only earns its place if it beats the random walk (skill_vs_rw > 0) at that horizon.
  * NO naive sqrt-time vol. Horizon vol = sigma_daily * sqrt(H * VR(H)) using the Lo-MacKinlay variance
    ratio (metrics.variance_ratio): VR=1 recovers sqrt-time, VR<1 (mean-revert) narrows, VR>1 widens.
  * Bands: empirical/conformal from horizon residuals when available; parametric only as a flagged fallback.
  * Defaults (confirmed): half-life FITTED via metrics.half_life (fallback 3); sigma_daily = EWMA/simple
    BLEND (metrics.ewma_vol); caps in CALIBRATED units (multiple of horizon vol), not sqrt-time; clustered
    standardized-miss is an ADDITIONAL regime signal (combine with ICSS/PSI/HMM upstream); crypto -> calendar
    sessions with 24h-return vol (explicit).

Reuses the canonical metrics library (single source of truth; check-duplication.mjs enforces it).
"""
import json, math, os
from metrics import half_life, ewma_vol, variance_ratio, stdev, _logret, _clean

PRESETS = {
    "cadence": [1, 5, 10, 21, 63],     # day / week / 2-week / month / quarter — maps to real market cadence
    "fib": [1, 2, 3, 5, 8, 13, 21],    # quasi-geometric grid; NOT a predictive law
    "powers": [1, 2, 4, 8, 16],
}


def horizons(preset="cadence"):
    return list(PRESETS.get(preset, PRESETS["cadence"]))


# ---- Default #1: fitted half-life (OU), fallback 3 ----
def fit_halflife(closes, fallback=3.0):
    hl = half_life(closes)
    return hl if (hl is not None and hl > 0) else fallback


def retention(hl):
    return 0.5 ** (1.0 / hl) if hl and hl > 0 else 0.0


def decayed_edge(edge_per_session, hl, H):
    """Cumulative decayed log-drift over H sessions: edge * sum_{k=0}^{H-1} r^k, r = 0.5^(1/halflife)."""
    r = retention(hl)
    if H <= 0:
        return 0.0
    if abs(1.0 - r) < 1e-12:
        return edge_per_session * H
    return edge_per_session * (1.0 - r ** H) / (1.0 - r)


# ---- Default #2: blended EWMA + simple daily vol ----
def blended_sigma_daily(rets, window=20, lam=0.94, w_ewma=0.5):
    v = rets[-window:] if len(rets) >= window else rets
    simple = stdev(v)
    ew = ewma_vol(rets, lam=lam, annualize=0)   # per-period (daily), not annualized
    if simple != simple:
        simple = ew
    if ew != ew:
        ew = simple
    if simple != simple and ew != ew:
        return float("nan")
    return w_ewma * ew + (1.0 - w_ewma) * simple


# ---- Variance-ratio-corrected horizon vol (replaces naive sqrt-time) ----
def horizon_sigma(closes, H, sigma_d):
    if H <= 1:
        return sigma_d
    vr = variance_ratio(closes, q=H)          # None if insufficient data
    if vr is None or vr <= 0:
        vr = 1.0                              # graceful fallback == sqrt-time
    return sigma_d * math.sqrt(H * vr)


def _quantile(xs, q):
    s = sorted(xs)
    if not s:
        return 0.0
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _emp_interval(resids, alpha=0.90):
    a = (1.0 - alpha) / 2.0
    return _quantile(resids, a), _quantile(resids, 1.0 - a)


# ---- Phase 1: coherent multi-horizon projection ----
def project(price_now, edge_per_session, closes, horizon_list,
            hl=None, z=1.0, cap_mult=2.0, alpha=0.90, resid_by_H=None):
    """One coherent log-space projection sampled at each horizon. Returns a list of per-horizon dicts.
    edge_per_session is the 1-session base log-drift signal (decayed over H). Bands conformal-if-available."""
    assert price_now > 0, "price_now must be > 0"
    rets = _logret(closes)
    sigma_d = blended_sigma_daily(rets)
    if hl is None:
        hl = fit_halflife(closes)
    p0 = math.log(price_now)
    out = []
    for H in horizon_list:
        sH = horizon_sigma(closes, H, sigma_d)
        mu = decayed_edge(edge_per_session, hl, H)
        cap = cap_mult * sH                      # Default #3: cap in CALIBRATED units, not sqrt-time
        capped = abs(mu) > cap
        mu_c = max(-cap, min(cap, mu)) if cap == cap else mu
        proj_log = p0 + mu_c
        rby = (resid_by_H or {}).get(H)
        if rby and len(rby) >= 8:
            lo_q, hi_q = _emp_interval(rby, alpha)
            lo, hi, method = math.exp(proj_log + lo_q), math.exp(proj_log + hi_q), "conformal"
        else:
            lo, hi, method = math.exp(proj_log - z * sH), math.exp(proj_log + z * sH), "parametric"
        out.append({"H": H, "projLog": proj_log, "projPrice": math.exp(proj_log),
                    "muLog": mu_c, "sigmaH": sH, "capped": bool(capped),
                    "lo": lo, "hi": hi, "bandMethod": method})
    return out


# ---- Phase 2: forecast scoring (immutable point-in-time; caller supplies the matched realized close) ----
def score(price_now, proj_log, sigma_H, realized_close):
    """All errors in log space + the decisive skill-vs-random-walk number (>0 => the model beat RW)."""
    p0 = math.log(price_now); ry = math.log(realized_close)
    log_err = ry - proj_log
    rw_err = ry - p0                                  # random-walk forecast = price_now
    proj_move = proj_log - p0; real_move = ry - p0
    return {
        "dollarErr": realized_close - math.exp(proj_log),
        "pctErr": math.exp(ry - proj_log) - 1.0,
        "logErr": log_err,
        "zErr": (log_err / sigma_H) if sigma_H and sigma_H > 0 else float("nan"),
        "dirHit": 1 if (proj_move == 0 and real_move == 0) or (proj_move * real_move > 0) else 0,
        "magRatio": (real_move / proj_move) if abs(proj_move) > 1e-12 else float("nan"),
        "skillVsRW": (1.0 - abs(log_err) / abs(rw_err)) if abs(rw_err) > 1e-12 else float("nan"),
    }


def rolling_bias(z_errors):
    v = _clean(z_errors)
    return sum(v) / len(v) if v else float("nan")


def clustered_miss(z_errors, k=3, thr=1.5):
    """ADDITIONAL regime signal (combine upstream with ICSS/GARCH regime + drift_store PSI/KS + HMM):
    last k standardized errors all exceed thr in magnitude AND share a sign => clustered directional miss."""
    v = _clean(z_errors)
    if len(v) < k:
        return False
    tail = v[-k:]
    return all(abs(x) > thr for x in tail) and (all(x > 0 for x in tail) or all(x < 0 for x in tail))


# ---- immutable forecast record (matches schemas/fib_forecast.schema.json) ----
def build_record(asof, asset_class, preset, price_now, projections, target_dates, params):
    items = []
    for p, td in zip(projections, target_dates):
        d = dict(p); d["targetDate"] = td
        items.append(d)
    return {"schemaVersion": "1.0", "asof": asof, "assetClass": asset_class,
            "horizonPreset": preset, "priceNow": price_now, "params": params, "horizons": items}


# ---- deterministic golden fixture (committed; both languages read it) ----
def _mul32(seed):
    a = seed & 0xFFFFFFFF
    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def gen_fixture():
    r = _mul32(20260627)
    closes = [100.0]
    for _ in range(140):
        closes.append(round(closes[-1] * math.exp(0.0004 + 0.012 * (r() - 0.5)), 6))
    hist, realized = closes[:120], closes[120]          # forecast from t=120, score against next close
    rets = _logret(hist)
    edge = sum(rets[-5:]) / 5.0                          # simple 5-session momentum drift
    hl = fit_halflife(hist)
    hz = horizons("cadence")
    proj = project(closes[119] if False else hist[-1], edge, hist, hz, hl=hl)
    sc = score(hist[-1], proj[0]["projLog"], proj[0]["sigmaH"], realized)
    expected = {"halflife": hl, "sigmaDaily": blended_sigma_daily(rets),
                "projections": proj, "score_H1": sc}
    return {"fixture_version": 1, "case": "fib-phase1-2-core",
            "inputs": {"closes_hist": hist, "realized_next": realized, "edge": edge, "preset": "cadence"},
            "expected": expected}


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fib_golden.json")
    json.dump(gen_fixture(), open(out, "w"), separators=(",", ":"))
    print("wrote", os.path.normpath(out))


if __name__ == "__main__":
    main()
