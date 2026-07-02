#!/usr/bin/env python3
"""predictive_cdf.py — a SAMPLE-BASED predictive distribution so CRPS/PIT are computed against a REAL
predictive CDF instead of a Gaussian centerline (the Anti-Deviation spec's "disable distribution metrics
unless a genuine predictive CDF exists" rule).

Construction: draw the predictive as  Y^(m) = mu + sigma * Z^(m), where {Z^(m)} are MATURED studentized
residuals (heavy-tailed, skewed — whatever the series actually is). The bulk CDF is the empirical CDF of
the samples (linear-interpolated); the tails are OPTIONALLY spliced with a Generalized-Pareto (POT) fit so
extreme quantiles extrapolate instead of clipping at the sample max/min. Scoring:
  * crps_sample(y): the proper energy-form CRPS  E|Y-y| - 0.5 E|Y-Y'|  (exact, sorted O(M log M)).
  * randomized_pit(y): PIT that is Uniform(0,1) under calibration (randomized to stay uniform for ties).
Pure stdlib + deterministic (seeded). No I/O."""
import math
import random

CDF_VERSION = "sample_v1"


def _gpd_mom(exceed):
    """Method-of-moments GPD fit to non-negative exceedances -> (xi, beta). Valid for xi < 0.5;
    falls back to exponential (xi=0) on degenerate variance. Returns None if too few points."""
    x = [e for e in exceed if e >= 0]
    n = len(x)
    if n < 10:
        return None
    m = sum(x) / n
    if m <= 0:
        return None
    v = sum((e - m) ** 2 for e in x) / (n - 1)
    if v <= 1e-12:
        return (0.0, m)                      # degenerate -> exponential tail
    r = m * m / v
    xi = 0.5 * (1.0 - r)
    beta = 0.5 * m * (r + 1.0)
    if beta <= 0:
        return (0.0, m)
    xi = max(-0.5, min(xi, 0.45))            # keep finite variance / stable extrapolation
    return (xi, beta)


def _gpd_cdf(x, xi, beta):
    if x <= 0:
        return 0.0
    if abs(xi) < 1e-8:
        return 1.0 - math.exp(-x / beta)
    z = 1.0 + xi * x / beta
    if z <= 0:
        return 1.0
    return 1.0 - z ** (-1.0 / xi)


def _gpd_q(p, xi, beta):
    p = min(max(p, 0.0), 1.0 - 1e-12)
    if abs(xi) < 1e-8:
        return -beta * math.log(1.0 - p)
    return (beta / xi) * ((1.0 - p) ** (-xi) - 1.0)


class PredictiveCDF:
    def __init__(self, mu, sigma, z_samples, gpd_tails=False, thresh_q=0.90, version=CDF_VERSION):
        """mu/sigma: location & scale (e.g. adjusted centerline + adjusted horizon sigma).
        z_samples : matured studentized residuals (the empirical shape). gpd_tails: splice POT tails."""
        zs = [float(z) for z in (z_samples or []) if z == z and abs(z) != float("inf")]
        if len(zs) < 20 or not (sigma and sigma > 0):
            raise ValueError("PredictiveCDF needs >=20 finite z-samples and sigma>0")
        self.mu = float(mu); self.sigma = float(sigma)
        self.samples = sorted(mu + self.sigma * z for z in zs)
        self.n = len(self.samples)
        self.version = version
        self.gpd_tails = bool(gpd_tails)
        self._up = self._lo = None
        if self.gpd_tails:
            qthi = self._emp_q(thresh_q); qtlo = self._emp_q(1.0 - thresh_q)
            self._uthr = qthi; self._lthr = qtlo
            self._pu = sum(1 for s in self.samples if s > qthi) / self.n            # P(Y>uthr)
            self._pl = sum(1 for s in self.samples if s < qtlo) / self.n            # P(Y<lthr)
            self._up = _gpd_mom([s - qthi for s in self.samples if s > qthi])
            self._lo = _gpd_mom([qtlo - s for s in self.samples if s < qtlo])

    def _emp_q(self, p):
        p = min(max(p, 0.0), 1.0); a = self.samples
        idx = p * (self.n - 1); lo = int(math.floor(idx)); hi = min(lo + 1, self.n - 1); f = idx - lo
        return a[lo] * (1 - f) + a[hi] * f

    def _emp_cdf(self, x):
        a = self.samples
        if x <= a[0]:
            return 0.0
        if x >= a[-1]:
            return 1.0
        lo, hi = 0, self.n - 1                       # binary search for interp bracket
        while hi - lo > 1:
            m = (lo + hi) // 2
            if a[m] <= x: lo = m
            else: hi = m
        span = a[hi] - a[lo]
        frac = 0.0 if span <= 0 else (x - a[lo]) / span
        return (lo + frac) / (self.n - 1)

    def cdf(self, x):
        if self.gpd_tails:
            if self._up and x > self._uthr:
                return (1.0 - self._pu) + self._pu * _gpd_cdf(x - self._uthr, *self._up)
            if self._lo and x < self._lthr:
                return self._pl * (1.0 - _gpd_cdf(self._lthr - x, *self._lo))
        return self._emp_cdf(x)

    def quantile(self, p):
        p = min(max(p, 1e-9), 1.0 - 1e-9)
        if self.gpd_tails:
            if self._up and p > (1.0 - self._pu):
                return self._uthr + _gpd_q((p - (1.0 - self._pu)) / self._pu, *self._up)
            if self._lo and p < self._pl:
                return self._lthr - _gpd_q((self._pl - p) / self._pl, *self._lo)
        return self._emp_q(p)

    def crps_sample(self, y):
        """Proper CRPS from the sample distribution: E|Y-y| - 0.5 E|Y-Y'|.
        Uses the sorted-sample identity  E|Y-Y'| = (2/M^2) sum_i (2i-M-1) Y_(i)  (1-indexed)."""
        a = self.samples; M = self.n
        e_abs = sum(abs(s - y) for s in a) / M
        s2 = 0.0
        for i, s in enumerate(a, start=1):
            s2 += (2 * i - M - 1) * s
        e_pair = (2.0 / (M * M)) * s2
        return e_abs - 0.5 * e_pair

    def randomized_pit(self, y, u=None):
        """Randomized PIT: plo + U*(phi-plo). Uniform(0,1) under calibration even with ties."""
        a = self.samples; M = self.n
        lt = sum(1 for s in a if s < y); le = sum(1 for s in a if s <= y)
        plo = lt / M; phi = le / M
        if u is None:
            u = random.Random(hash((round(y, 6), M)) & 0x7fffffff).random()
        return plo + u * (phi - plo)


def crps_gaussian(mu, sigma, y):
    """Reference Gaussian CRPS (closed form) for comparison / the centerline path."""
    if not (sigma and sigma > 0):
        return abs(y - mu)
    z = (y - mu) / sigma
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return sigma * (z * (2 * cdf - 1) + 2 * pdf - 1.0 / math.sqrt(math.pi))
