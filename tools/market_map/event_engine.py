"""event_engine.py — quantitative event-study math for SEC filings (8-K / 13D / 13G / Form 3-4-5).

Turns dated filing events into NUMBERS the board and cone can use. Pure stdlib; verified against planted
structure; 1:1 JS port for the browser. Research only, not advice.

EQUATIONS
---------
1. Market-model abnormal returns (event study, MacKinlay 1997):
     estimation window before the event -> OLS  r_i,t = a + b*r_m,t + e_t
     AR_t   = r_i,t - (a + b*r_m,t)                     (abnormal return)
     CAR(τ1,τ2) = Σ_{t=τ1}^{τ2} AR_t                    (cumulative abnormal return)
     SCAR   = CAR / ( σ_AR * sqrt(τ2-τ1+1) )            (standardized; ~ t under H0)
     where σ_AR = std of AR over the estimation window.

2. Event-intensity (self-exciting / Hawkes-style exponential decay):
     I(t) = Σ_{e: t_e ≤ t}  s(type_e) * exp( -(t - t_e) / τ )
     s(type) = severity weight; τ = decay in trading days. Recent, severe clusters -> high I.

3. 8-K item severity s ∈ [0,1] by item code (materiality): restatement/bankruptcy high, "other" low.

4. 13D/13G stake signal:
     stake = clamp( sign * (g(form) * Δpct/5 + 0.4*new) , -1, 1 )
     13D (activist, >5%, intent) weighted higher than 13G (passive); Δpct = change in ownership %.

5. Insider net ratio (Form 3/4/5), 10b5-1 planned sells down-weighted by ρ:
     netInsider = ( buyVal - w_sell ) / ( buyVal + w_sell + ε ),
     w_sell = discSell + ρ*planSell                      (ρ≈0.35)

6. Combined event tilt (the number added to expected return, in %):
     eventTilt = θ1*tanh(CAR/k1) + θ2*tanh(I/k2) + θ3*stake + θ4*netInsider,  clamped to ±cap
"""
import math

__all__ = ["ols2", "abnormal_returns", "car", "scar", "event_intensity", "EIGHTK_SEVERITY",
           "eightk_severity", "stake_signal", "insider_net", "event_tilt"]

# 8-K item severity (materiality); keys are item codes as strings.
EIGHTK_SEVERITY = {
    "1.01": 0.55, "1.02": 0.55, "1.03": 0.95,   # entry/exit material agreement; bankruptcy
    "2.01": 0.70, "2.02": 0.60, "2.03": 0.45, "2.04": 0.60, "2.05": 0.55, "2.06": 0.80,  # M&A; results; debt; impairment
    "3.01": 0.65, "3.02": 0.40, "3.03": 0.45,   # delisting; unreg sales; rights mods
    "4.01": 0.85, "4.02": 0.95,                 # auditor change; non-reliance/RESTATEMENT
    "5.01": 0.70, "5.02": 0.55, "5.03": 0.30, "5.07": 0.25,  # control change; officer dep.; bylaws; votes
    "7.01": 0.30, "8.01": 0.25,                 # Reg FD; other events
}


def eightk_severity(items):
    """Max severity over the 8-K item codes on a filing (a filing can carry several items)."""
    best = 0.0
    for it in (items or []):
        best = max(best, EIGHTK_SEVERITY.get(str(it).strip(), 0.25))
    return best


def ols2(x, y):
    """Simple OLS y = a + b x. Returns (a, b)."""
    n = len(x)
    if n < 2:
        return (sum(y) / n if n else 0.0), 0.0
    mx = sum(x) / n; my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    b = sxy / sxx if sxx > 0 else 0.0
    a = my - b * mx
    return a, b


def abnormal_returns(ri, rm, est_lo, est_hi, ev_lo, ev_hi):
    """Fit the market model on [est_lo,est_hi) and return (AR_event[], sigmaAR) over [ev_lo,ev_hi]."""
    xe = rm[est_lo:est_hi]; ye = ri[est_lo:est_hi]
    a, b = ols2(xe, ye)
    resid = [ye[i] - (a + b * xe[i]) for i in range(len(ye))]
    n = len(resid)
    if n > 2:
        m = sum(resid) / n
        sigma = math.sqrt(sum((r - m) ** 2 for r in resid) / (n - 2))
    else:
        sigma = 0.0
    ar = [ri[t] - (a + b * rm[t]) for t in range(ev_lo, ev_hi + 1)]
    return ar, sigma, a, b


def car(ar):
    return sum(ar)


def scar(ar, sigma):
    n = len(ar)
    if n == 0 or sigma <= 0:
        return 0.0
    return sum(ar) / (sigma * math.sqrt(n))


def event_intensity(events, t_now, tau=10.0):
    """events: list of (t_e, severity). I(t) = Σ s * exp(-(t_now - t_e)/tau) for t_e <= t_now."""
    I = 0.0
    for te, s in events:
        if te <= t_now:
            I += s * math.exp(-(t_now - te) / tau)
    return I


def stake_signal(form, dpct, is_new, sign=1):
    """13D/13G stake signal in [-1,1]. form='13D'(activist) or '13G'(passive); dpct=Δ ownership %."""
    g = 1.0 if str(form).upper().startswith("13D") else 0.45
    raw = sign * (g * (dpct / 5.0) + (0.4 if is_new else 0.0) * g)
    return max(-1.0, min(1.0, raw))


def insider_net(buy_val, disc_sell, plan_sell, rho=0.35):
    """Insider net ratio in [-1,1]; planned (10b5-1) sells down-weighted by rho."""
    w_sell = disc_sell + rho * plan_sell
    denom = buy_val + w_sell + 1e-9
    return (buy_val - w_sell) / denom


def event_tilt(car_val, intensity, stake, netins, k1=0.05, k2=2.0,
               th=(0.6, 0.4, 0.5, 0.5), cap=3.0):
    """Combined event tilt in PERCENT (added to expected return). Bounded by ±cap."""
    t1, t2, t3, t4 = th
    val = (t1 * math.tanh(car_val / k1) + t2 * math.tanh(intensity / k2)
           + t3 * stake + t4 * netins)
    return max(-cap, min(cap, val))
