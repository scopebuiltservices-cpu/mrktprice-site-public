"""proj_server.py — server-side reproduction of the terminal cone's central-path drift (OU mean-reversion
+ EMA-slope momentum blend), so the universe-wide projledger learns the SAME forecast family the browser
shows (not the weak pure-momentum proxy). No-lookahead by construction (uses only data up to t). Verified."""
import math

__all__ = ["ou_fit", "ou_drift", "ema_slope_logret", "blend_drift"]


def ou_fit(logprices):
    """AR(1) on log-price: lnP_t = a + b*lnP_{t-1} + e. Returns {theta, mu, b}. theta=-ln(b) is the
    mean-reversion speed; mu=a/(1-b) is the long-run log-price level. b clamped to (0,0.9999) for stability."""
    n = len(logprices)
    if n < 30:
        return {"theta": 0.0, "mu": (logprices[-1] if logprices else 0.0), "b": 1.0}
    x = logprices[:-1]; y = logprices[1:]
    m = len(x); mx = sum(x) / m; my = sum(y) / m
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(m))
    b = (sxy / sxx) if sxx > 0 else 1.0
    b = max(1e-6, min(0.9999, b))
    a = my - b * mx
    mu = a / (1.0 - b)
    theta = -math.log(b)
    return {"theta": theta, "mu": mu, "b": b}


def ou_drift(logprice_now, ou, H):
    """Expected H-step log-return under the fitted OU: (mu - lnP_now)*(1 - exp(-theta*H))."""
    return (ou["mu"] - logprice_now) * (1.0 - math.exp(-ou["theta"] * H))


def ema_slope_logret(logprices, span=21):
    """Per-step slope of an EMA of log-price over the last `span` points (a momentum drift estimate)."""
    n = len(logprices)
    if n < span + 2:
        return 0.0
    k = 2.0 / (span + 1.0)
    e = logprices[0]
    es = []
    for p in logprices:
        e = e + k * (p - e); es.append(e)
    seg = es[-span:]
    return (seg[-1] - seg[0]) / max(1, (len(seg) - 1))


def blend_drift(closes, H, w_ou=0.65, w_mom=0.35, cap_sigma=2.0, span=21):
    """Cone-style central drift over H: blend OU reversion + EMA momentum, capped at +-cap_sigma*sigma_H.
    Returns the expected H-step log-return (no lookahead: uses closes[:t] only when called per-bar)."""
    lp = [math.log(c) for c in closes if c > 0]
    if len(lp) < 30:
        return 0.0
    r = [lp[i] - lp[i - 1] for i in range(1, len(lp))]
    sd = math.sqrt(sum(x * x for x in r) / len(r)) or 1e-6
    ou = ou_fit(lp)
    d_ou = ou_drift(lp[-1], ou, H)
    d_mom = ema_slope_logret(lp, span) * H
    d = w_ou * d_ou + w_mom * d_mom
    lim = cap_sigma * sd * math.sqrt(H)
    return max(-lim, min(lim, d))
