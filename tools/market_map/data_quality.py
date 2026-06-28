#!/usr/bin/env python3
"""
data_quality.py — data-integrity + drift sentinel (pure stdlib, unit-tested).

The point of this layer is honesty under bad inputs: when a data pull is skewed (outliers, stale/stuck
feed, gaps), when two sources disagree, when the distribution drifts versus the reference window, or when
an estimator returns a non-finite / implausible value, the system should DEGRADE and LABEL — never ship a
confident-looking wrong number. Everything here is robust (median/MAD based) and returns explicit reasons.

Components
  series_health(closes, vols, dates)  -> dict: NaN/non-positive counts, longest stale run, MAD jump
      outliers, max calendar gap, sample skew/kurtosis, verdict in {clean, degraded, reject}
  cross_source_agree(a, b, tol)       -> dict: do two overlapping series agree within tol (rel. dev)?
  psi(ref, cur, bins)                 -> Population Stability Index (distribution drift)
  ks_stat(ref, cur)                   -> two-sample Kolmogorov-Smirnov distance
  drift_report(ref, cur)              -> {psi, ks, level in {stable, moderate, significant}}
  winsorize(x, p)                     -> tail-clipped copy (pre-fit hardening)
  robust_z(x)                         -> Iglewicz-Hoaglin modified z (0.6745*(x-med)/MAD)
  guard(value, lo, hi, name)          -> (value or None, reason): finite + in-bounds check for outputs
"""
import math

_MAD_K = 0.6745  # makes MAD a consistent estimator of sigma for normal data (Iglewicz-Hoaglin)


def _finite(xs):
    return [float(x) for x in xs if x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))]


def _median(xs):
    s = sorted(xs); n = len(s)
    if n == 0:
        return None
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


def winsorize(x, p=0.02):
    """Clip to the [p, 1-p] empirical quantiles. Hardens a series before fitting so a few wild ticks
    don't dominate a regression/IC (the spec's pre-rank winsorize step)."""
    v = _finite(x)
    if len(v) < 5 or p <= 0:
        return list(x)
    s = sorted(v)
    lo = s[int(p * (len(s) - 1))]; hi = s[int((1 - p) * (len(s) - 1))]
    return [min(max(float(xi), lo), hi) if (xi is not None and math.isfinite(float(xi))) else xi for xi in x]


def robust_z(x):
    """Modified z-scores via median/MAD. |z| > 3.5 is the conventional outlier flag (robust to the very
    outliers a mean/std z would be corrupted by)."""
    v = _finite(x)
    if len(v) < 3:
        return [0.0] * len(x)
    med = _median(v)
    mad = _median([abs(xi - med) for xi in v]) or 1e-12
    return [(_MAD_K * (float(xi) - med) / mad) if (xi is not None and math.isfinite(float(xi))) else 0.0 for xi in x]


def _returns(closes):
    c = _finite(closes)
    return [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0 and c[i] > 0]


def _skew_kurt(xs):
    n = len(xs)
    if n < 3:
        return 0.0, 3.0
    mu = sum(xs) / n
    m2 = sum((x - mu) ** 2 for x in xs) / n
    if m2 <= 0:
        return 0.0, 3.0
    m3 = sum((x - mu) ** 3 for x in xs) / n
    m4 = sum((x - mu) ** 4 for x in xs) / n
    sd = math.sqrt(m2)
    return m3 / sd ** 3, m4 / m2 ** 2


def longest_stale_run(closes):
    """Longest run of identical consecutive closes — a stuck/duplicated feed signature."""
    best = run = 1
    prev = None
    for c in closes:
        if prev is not None and c == prev:
            run += 1; best = max(best, run)
        else:
            run = 1
        prev = c
    return best if closes else 0


def _max_gap_days(dates):
    """Largest calendar gap (in days) between consecutive ISO dates; ignores weekends only loosely."""
    import datetime
    ds = []
    for d in dates or []:
        try:
            ds.append(datetime.date.fromisoformat(str(d)[:10]))
        except Exception:
            pass
    if len(ds) < 2:
        return None
    ds.sort()
    return max((ds[i] - ds[i - 1]).days for i in range(1, len(ds)))


def series_health(closes, vols=None, dates=None, *, min_len=40, max_stale=4, max_gap_days=7, jump_z=3.5):
    """Robust health check of one price series. verdict: reject (unusable) / degraded (use with caution) /
    clean. Returns counts + reasons so the caller can label the name instead of silently trusting it."""
    raw = list(closes or [])
    n = len(raw)
    n_nan = sum(1 for c in raw if c is None or not isinstance(c, (int, float)) or not math.isfinite(float(c)))
    fin = _finite(raw)
    n_nonpos = sum(1 for c in fin if c <= 0)
    stale = longest_stale_run([c for c in fin if c > 0])
    rets = _returns(raw)
    rz = robust_z(rets)
    jumps = sum(1 for z in rz if abs(z) > jump_z)
    gap = _max_gap_days(dates)
    skew, kurt = _skew_kurt(rets)
    reasons = []
    if n < min_len:
        reasons.append("too few bars (%d<%d)" % (n, min_len))
    if n_nan:
        reasons.append("%d non-finite closes" % n_nan)
    if n_nonpos:
        reasons.append("%d non-positive closes" % n_nonpos)
    if stale >= max_stale:
        reasons.append("stale run %d (stuck feed?)" % stale)
    if gap is not None and gap > max_gap_days:
        reasons.append("max date gap %dd" % gap)
    # verdict
    if n < min_len or n_nonpos or n_nan > max(2, 0.02 * n):
        verdict = "reject"
    elif reasons or jumps > max(3, 0.05 * len(rets)):
        verdict = "degraded"
    else:
        verdict = "clean"
    return {"n": n, "nNaN": n_nan, "nNonPos": n_nonpos, "staleRun": stale, "jumpOutliers": jumps,
            "maxGapDays": gap, "skew": round(skew, 3), "kurt": round(kurt, 3),
            "verdict": verdict, "reasons": reasons}


def cross_source_agree(a, b, tol=0.02, n=20):
    """Do two price series agree on their overlapping tail within `tol` relative deviation? Catches a
    source serving wrong/shifted prices (skew between providers). Returns {agree, maxRelDev, n}."""
    fa = _finite(a); fb = _finite(b)
    k = min(len(fa), len(fb), n)
    if k < 3:
        return {"agree": None, "maxRelDev": None, "n": k, "reason": "insufficient overlap"}
    ta = fa[-k:]; tb = fb[-k:]
    dev = max(abs(ta[i] - tb[i]) / abs(tb[i]) for i in range(k) if tb[i] != 0)
    return {"agree": dev <= tol, "maxRelDev": round(dev, 5), "n": k, "tol": tol}


def psi(ref, cur, bins=10):
    """Population Stability Index between a reference and current sample. Bins from ref quantiles.
    <0.10 stable, 0.10-0.25 moderate drift, >0.25 significant drift. Returns None if too little data."""
    r = _finite(ref); c = _finite(cur)
    if len(r) < bins * 2 or len(c) < bins:
        return None
    s = sorted(r)
    edges = [s[min(int(q / bins * (len(s) - 1)), len(s) - 1)] for q in range(1, bins)]
    edges = [-math.inf] + edges + [math.inf]

    def hist(xs):
        h = [0] * (len(edges) - 1)
        for x in xs:
            for i in range(len(edges) - 1):
                if edges[i] < x <= edges[i + 1]:
                    h[i] += 1; break
        tot = sum(h) or 1
        return [(hi / tot) for hi in h]
    pr = hist(r); pc = hist(c)
    eps = 1e-6
    return sum((pc[i] - pr[i]) * math.log((pc[i] + eps) / (pr[i] + eps)) for i in range(len(pr)))


def ks_stat(ref, cur):
    """Two-sample Kolmogorov-Smirnov distance = max |F_ref - F_cur|. Distribution-shape drift detector."""
    r = sorted(_finite(ref)); c = sorted(_finite(cur))
    if len(r) < 5 or len(c) < 5:
        return None
    allv = sorted(set(r + c))

    def cdf(s, x):
        import bisect
        return bisect.bisect_right(s, x) / len(s)
    return max(abs(cdf(r, x) - cdf(c, x)) for x in allv)


def drift_report(ref, cur, bins=10):
    """Combine PSI + KS into a single drift verdict for a returns series (ref vs current window)."""
    p = psi(ref, cur, bins); k = ks_stat(ref, cur)
    level = "unknown"
    if p is not None:
        level = "stable" if p < 0.10 else ("moderate" if p < 0.25 else "significant")
    return {"psi": (round(p, 4) if p is not None else None),
            "ks": (round(k, 4) if k is not None else None), "level": level}


def guard(value, lo=None, hi=None, name="value"):
    """Output guard for an estimator: returns (value, None) if finite and within [lo,hi]; otherwise
    (None, reason). Use this to stop a broken/degenerate equation from emitting a confident wrong number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None, "%s not numeric" % name
    if not math.isfinite(v):
        return None, "%s non-finite" % name
    if lo is not None and v < lo:
        return None, "%s %.4g < %.4g" % (name, v, lo)
    if hi is not None and v > hi:
        return None, "%s %.4g > %.4g" % (name, v, hi)
    return v, None
