"""Verified Black-Scholes-Merton engine for MrktPrice (pure stdlib).

Black-Scholes prices OPTIONS, not stocks. There is no "BS fair price of a stock".
What this module gives, per (S, K, T, r, sigma, q):
  - bs_price : European call/put theoretical value (continuous dividend yield q)
  - greeks   : delta, gamma, vega, theta (per-year and per-day), rho
  - implied_vol : invert market option price -> sigma (Newton + bisection fallback)
And, tying an option to its SAME-TICKER stock:
  - value_chain : price every contract from the stock's own spot, solve missing IV,
                  and measure market-vs-model richness (market_mid - bs_value).

Accuracy: N(.) is the exact normal CDF via math.erf, so prices match references to
machine precision given identical inputs. The only modelling choices are r (risk-free),
q (dividend yield) and sigma — pass good ones (risk-free curve, trailing div yield,
market IV) for the result to be economically correct, not just arithmetically exact.
Research/education only — not trading advice.
"""
from __future__ import annotations
import math

SQRT2PI = math.sqrt(2.0 * math.pi)

def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI

def norm_cdf(x: float) -> float:
    # exact Gaussian CDF via the error function
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def _d1_d2(S, K, T, r, sigma, q):
    srt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / srt
    return d1, d1 - srt

def _intrinsic(S, K, r, q, T, kind):
    fwd_S = S * math.exp(-q * T)
    disc_K = K * math.exp(-r * T)
    return max(fwd_S - disc_K, 0.0) if kind == "C" else max(disc_K - fwd_S, 0.0)

def bs_price(S, K, T, r, sigma, q=0.0, kind="C"):
    """European Black-Scholes-Merton price. kind 'C' or 'P'."""
    kind = str(kind).upper()[:1]
    if S <= 0 or K <= 0:
        return 0.0
    if T <= 0 or sigma <= 0:           # degenerate -> discounted intrinsic
        return _intrinsic(S, K, r, q, max(T, 0.0), kind)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    dfq, dfr = math.exp(-q * T), math.exp(-r * T)
    if kind == "C":
        return S * dfq * norm_cdf(d1) - K * dfr * norm_cdf(d2)
    return K * dfr * norm_cdf(-d2) - S * dfq * norm_cdf(-d1)

def greeks(S, K, T, r, sigma, q=0.0, kind="C"):
    """Full first/second-order greeks. vega/rho per 1.00 (×0.01 for per-1%);
    theta returned per-year and per-calendar-day."""
    kind = str(kind).upper()[:1]
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0,
                "theta": 0.0, "thetaDay": 0.0, "rho": 0.0}
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    dfq, dfr = math.exp(-q * T), math.exp(-r * T)
    pdf = norm_pdf(d1)
    gamma = dfq * pdf / (S * sigma * math.sqrt(T))
    vega = S * dfq * pdf * math.sqrt(T)            # per 1.00 vol; ×0.01 = per vol point
    if kind == "C":
        delta = dfq * norm_cdf(d1)
        theta = (-S * dfq * pdf * sigma / (2 * math.sqrt(T))
                 - r * K * dfr * norm_cdf(d2) + q * S * dfq * norm_cdf(d1))
        rho = K * T * dfr * norm_cdf(d2)
    else:
        delta = -dfq * norm_cdf(-d1)
        theta = (-S * dfq * pdf * sigma / (2 * math.sqrt(T))
                 + r * K * dfr * norm_cdf(-d2) - q * S * dfq * norm_cdf(-d1))
        rho = -K * T * dfr * norm_cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega,
            "theta": theta, "thetaDay": theta / 365.0, "rho": rho}

def implied_vol(price, S, K, T, r, q=0.0, kind="C", tol=1e-8, max_iter=100):
    """Solve sigma from a market price. Newton with vega; bisection fallback.
    Returns None if outside no-arbitrage bounds."""
    kind = str(kind).upper()[:1]
    if price is None or S <= 0 or K <= 0 or T <= 0 or price <= 0:
        return None
    intr = _intrinsic(S, K, r, q, T, kind)
    cap = (S * math.exp(-q * T)) if kind == "C" else (K * math.exp(-r * T))
    if price < intr - 1e-9 or price > cap + 1e-9:   # arbitrage-violating quote
        return None
    sigma = 0.25
    for _ in range(max_iter):
        diff = bs_price(S, K, T, r, sigma, q, kind) - price
        if abs(diff) < tol:
            return sigma
        v = greeks(S, K, T, r, sigma, q, kind)["vega"]
        if v < 1e-10:
            break
        step = diff / v
        sigma -= step
        if sigma <= 1e-6 or sigma > 10:
            break
    lo, hi = 1e-6, 10.0
    flo = bs_price(S, K, T, r, lo, q, kind) - price
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        fmid = bs_price(S, K, T, r, mid, q, kind) - price
        if abs(fmid) < tol:
            return mid
        if (flo < 0) != (fmid < 0):
            hi = mid
        else:
            lo, flo = mid, fmid
    return 0.5 * (lo + hi)

def realized_vol(closes, annualize=252):
    """Annualized close-to-close volatility from a price series (for IV-vs-RV richness)."""
    cl=[float(c) for c in (closes or []) if c not in (None,"") and float(c)>0]
    if len(cl)<3: return None
    rets=[__import__("math").log(cl[i]/cl[i-1]) for i in range(1,len(cl))]
    n=len(rets); m=sum(rets)/n
    var=sum((x-m)**2 for x in rets)/(n-1)
    return (var*annualize)**0.5

def value_chain(chain, spot, days, r=0.04, q=0.0, ref_vol=None, contract=100):
    """Price a SAME-TICKER chain from its own stock spot and measure market richness
    vs an INDEPENDENT reference vol (ref_vol = realized vol if given, else ATM IV).
    Each contract's greeks use its own market IV; bsValue/richness use ref_vol so the
    comparison is meaningful. chain: {strike,type 'C'/'P',oi,iv?,bid?,ask?,last?,mark?}.
    Returns {contracts:[...], summary:{...}} or None."""
    if not chain or spot<=0: return None
    T=max(days,1)/365.0
    rows=[]
    for o in chain:
        try:
            K=float(o["strike"]); kind=str(o.get("type","")).upper()[:1]
        except Exception: continue
        if K<=0 or kind not in ("C","P"): continue
        def _f(*keys):
            for k in keys:
                v=o.get(k)
                try:
                    if v not in (None,""): return float(v)
                except Exception: pass
            return None
        bid,ask=_f("bid"),_f("ask")
        mark=_f("mark") if _f("mark") is not None else (
            (bid+ask)/2 if (bid is not None and ask is not None) else _f("last","price"))
        iv=_f("iv","impliedVolatility")
        if (iv is None or iv<=0) and mark:
            iv=implied_vol(mark,spot,K,T,r,q,kind)
        rows.append((K,kind,_f("oi"),mark,iv))
    if not rows: return None
    # reference vol: realized vol if provided, else ATM market IV, else 0.30
    ivs=[(abs(K-spot),iv) for (K,kind,oi,mark,iv) in rows if iv and iv>0]
    atm_iv=sorted(ivs)[0][1] if ivs else None
    refv = ref_vol if (ref_vol and ref_vol>0) else (atm_iv if atm_iv else 0.30)
    out, rich = [], []
    for (K,kind,oi,mark,iv) in rows:
        sig_g = iv if (iv and iv>0) else refv          # greeks at the contract's own IV
        bsv = bs_price(spot,K,T,r,refv,q,kind)         # model value at the REFERENCE vol
        gk = greeks(spot,K,T,r,sig_g,q,kind)
        richness=(mark-bsv) if (mark is not None) else None
        rp=(100*richness/bsv) if (richness is not None and bsv>1e-6) else None
        out.append({"strike":K,"type":kind,"oi":oi,"mark":mark,
                    "iv":round(iv,4) if iv else None,
                    "ivPremPts":round((iv-refv)*100,2) if (iv and iv>0) else None,
                    "bsValue":round(bsv,4),
                    "richness":round(richness,4) if richness is not None else None,
                    "richnessPct":round(rp,2) if rp is not None else None,
                    "delta":round(gk["delta"],4),"gamma":round(gk["gamma"],6),
                    "vega":round(gk["vega"]*0.01,4),"thetaDay":round(gk["thetaDay"],4),
                    "rho":round(gk["rho"]*0.01,4)})
        if rp is not None: rich.append(rp)
    avg_rich=sum(rich)/len(rich) if rich else None
    summary={"spot":spot,"days":days,"r":r,"q":q,"n":len(out),
             "refVolPct":round(refv*100,1),"refVolSource":("realized" if (ref_vol and ref_vol>0) else "atm_iv"),
             "atmIVpct":round(atm_iv*100,1) if atm_iv else None,
             "expMovePct":round(atm_iv*(T**0.5)*100,2) if atm_iv else None,
             "avgRichnessPct":round(avg_rich,2) if avg_rich is not None else None,
             "verdict":(None if avg_rich is None else
                        ("options rich vs model" if avg_rich>2 else
                         "options cheap vs model" if avg_rich<-2 else "fairly priced"))}
    return {"contracts":out,"summary":summary}
