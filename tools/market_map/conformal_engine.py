"""conformal_engine.py — Conformalized Quantile Regression (CQR; Romano, Patterson & Candès 2019)
and finite-sample split-conformal helpers. Pure stdlib. Distribution-free FINITE-SAMPLE marginal
coverage >= 1-alpha for exchangeable calibration data, regardless of the base quantile model's quality.

The board already does asymmetric split-conformal in lineage.calibrate_horizon for the cone. CQR
generalizes that to *conditional* quantile predictions (q_lo(x), q_hi(x)) from any model: the conformal
pad widens (or tightens) the model's band by a single calibrated constant so realized coverage hits the
target on held-out data. Method only — no external feed."""
import math

__all__ = ["pinball_loss", "gaussian_quantiles", "cqr_scores", "cqr_pad", "cqr_interval",
           "interval_coverage", "interval_score", "cqr_calibrate_apply"]


def pinball_loss(y, q, tau):
    """Pinball (check) loss for a single quantile prediction q at level tau. Lower = better-calibrated."""
    d = y - q
    return tau * d if d >= 0 else (tau - 1.0) * d


def gaussian_quantiles(mu, sd, alpha=0.10):
    """Symmetric (1-alpha) Gaussian band [mu - z*sd, mu + z*sd], z = Phi^{-1}(1-alpha/2).
    A convenience base model so CQR has quantile predictions to conformalize."""
    z = _norm_ppf(1.0 - alpha / 2.0)
    return mu - z * sd, mu + z * sd


def cqr_scores(cal_qlo, cal_qhi, cal_y):
    """CQR nonconformity scores E_i = max(qlo_i - y_i, y_i - qhi_i). Negative when y_i is strictly
    inside the predicted band (model can be tightened); positive when outside (must be widened)."""
    n = len(cal_y)
    return [max(cal_qlo[i] - cal_y[i], cal_y[i] - cal_qhi[i]) for i in range(n)]


def cqr_pad(cal_qlo, cal_qhi, cal_y, alpha=0.10):
    """The conformal pad: the ceil((1-alpha)(n+1))-th smallest CQR score (finite-sample rank quantile).
    If that rank exceeds n the pad is +inf (too few calibration points to guarantee coverage)."""
    E = sorted(cqr_scores(cal_qlo, cal_qhi, cal_y))
    n = len(E)
    if n == 0:
        return float("inf")
    k = math.ceil((1.0 - alpha) * (n + 1))
    if k > n:
        return float("inf")
    return E[k - 1]


def cqr_interval(qlo, qhi, pad):
    """Apply the conformal pad to a (possibly new) quantile prediction: [qlo - pad, qhi + pad]."""
    return qlo - pad, qhi + pad


def interval_coverage(y, lo, hi):
    n = len(y)
    if n == 0:
        return 0.0
    return sum(1 for i in range(n) if lo[i] <= y[i] <= hi[i]) / n


def interval_score(y, lo, hi, alpha=0.10):
    """Mean Winkler/interval score (lower is better): width + asymmetric miss penalty."""
    n = len(y)
    if n == 0:
        return 0.0
    s = 0.0
    for i in range(n):
        w = hi[i] - lo[i]
        s += w
        if y[i] < lo[i]:
            s += (2.0 / alpha) * (lo[i] - y[i])
        elif y[i] > hi[i]:
            s += (2.0 / alpha) * (y[i] - hi[i])
    return s / n


def cqr_calibrate_apply(cal_qlo, cal_qhi, cal_y, test_qlo, test_qhi, alpha=0.10):
    """Convenience: compute pad on calibration, return conformalized test bands (lo[], hi[]) + pad."""
    pad = cqr_pad(cal_qlo, cal_qhi, cal_y, alpha)
    lo = [test_qlo[i] - pad for i in range(len(test_qlo))]
    hi = [test_qhi[i] + pad for i in range(len(test_qhi))]
    return lo, hi, pad


# --- Acklam inverse normal CDF (matches lineage._norm_ppf), stdlib only ---
def _norm_ppf(p):
    if p <= 0.0:
        return -float("inf")
    if p >= 1.0:
        return float("inf")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    if p <= 1.0 - pl:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
