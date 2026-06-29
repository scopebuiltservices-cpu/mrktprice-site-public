"""proj_engine.py — Fibonacci multi-horizon projection + accuracy (PDF 2). Direct/decayed projClose with a
normalized expected-path and honest accuracy scoring. Pure stdlib; verified; 1:1 JS port. Research only.

EQUATIONS
  phi = 0.5^(1/tau)                                   signal half-life decay factor (tau sessions)
  M(H,tau) = (1 - phi^H)/(1 - phi)                    cumulative decay multiplier (M(1)=1; ->H as tau->inf)
  edge1 = ln(projClose1D / priceNow)                  one-day log edge
  edge1c = clamp(edge1, +-capDaily*sigma1)            cap the daily edge
  muH = clamp(M(H,tau)*edge1c, +-capH*sigmaH)         horizon log-return forecast
  sigmaH = sigma1*sqrt(H)                             (fallback; replace with volterm term-structure)
  projCloseFwdH = priceNow*exp(muH)
  expectedPathPrice_H(e) = priceNowAtForecast*exp(w(e,H)*muH), w(e,H)=M(e,tau)/M(H,tau)  [path(H)=stored fc]
  signedLogError = ln(actual/storedForecast);  signedZError = signedLogError/sigmaH
  skillVsNaive = 1 - MAE_model/MAE_naive             (naive = priceNowAtForecast)
"""
import math

__all__ = ["cumulative_decay_multiplier", "build_fallback_projection", "expected_path_price",
           "score_accuracy", "skill_vs_naive", "prob_above_now"]


def cumulative_decay_multiplier(H, tau):
    if tau is None or tau <= 0:
        return float(H)
    phi = 0.5 ** (1.0 / tau)
    if abs(1.0 - phi) < 1e-12:
        return float(H)
    return (1.0 - phi ** H) / (1.0 - phi)


def build_fallback_projection(price_now, proj_close_1d, sigma_daily, H, half_life=3.0,
                              cap_daily_sigma=1.5, cap_horizon_sigma=2.0):
    if not (price_now > 0 and proj_close_1d > 0):
        return None
    edge1 = math.log(proj_close_1d / price_now)
    lim1 = cap_daily_sigma * sigma_daily
    edge1c = max(-lim1, min(lim1, edge1))
    M = cumulative_decay_multiplier(H, half_life)
    sigma_H = sigma_daily * math.sqrt(H)
    mu_raw = M * edge1c
    limH = cap_horizon_sigma * sigma_H
    mu_H = max(-limH, min(limH, mu_raw))
    proj = price_now * math.exp(mu_H)
    return {"H": H, "muH": mu_H, "sigmaH": sigma_H, "projCloseFwdH": proj,
            "pctVsNow": (math.exp(mu_H) - 1.0) * 100.0, "zEdgeH": (mu_H / sigma_H if sigma_H > 0 else 0.0),
            "M": M}


def expected_path_price(price_now_at_forecast, mu_H, elapsed, H, half_life=3.0):
    """Normalized so expected_path_price(H) == priceNow*exp(muH) (the stored forecast)."""
    mH = cumulative_decay_multiplier(H, half_life)
    me = cumulative_decay_multiplier(elapsed, half_life)
    w = (me / mH) if mH > 0 else 0.0
    return price_now_at_forecast * math.exp(w * mu_H)


def score_accuracy(actual_target_price, stored_forecast_price, sigma_H):
    sle = math.log(actual_target_price / stored_forecast_price)
    sz = (sle / sigma_H) if sigma_H > 0 else 0.0
    return {"signedLogError": sle, "signedZError": sz, "absZError": abs(sz)}


def skill_vs_naive(forecasts, actuals, price_now_at_forecast):
    """forecasts/actuals/priceNow aligned lists. skill = 1 - MAE_model/MAE_naive (naive = no change)."""
    n = len(forecasts)
    if n == 0:
        return 0.0
    mae_m = sum(abs(actuals[i] - forecasts[i]) for i in range(n)) / n
    mae_n = sum(abs(actuals[i] - price_now_at_forecast[i]) for i in range(n)) / n
    return (1.0 - mae_m / mae_n) if mae_n > 0 else 0.0


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_above_now(mu_H, sigma_H):
    return _ncdf(mu_H / sigma_H) if sigma_H > 0 else 0.5
