#!/usr/bin/env python3
"""Intraday 15-minute -> END-OF-DAY analytics (pure functions, unit-tested against planted structure).

Turns the live 15-minute stream (volume + returns) PLUS daily history into a projected end-of-day
outlook: close price, total volume, and day-% change, with intraday realized volatility compared to
the daily HV. Reference only; no look-ahead (every number uses bars <= now).

Core pieces
-----------
  intraday_rv(returns)                 realized vol from 15-min log returns (per-day + annualized)
  tod_volume_profile(n)                U-shaped time-of-day volume weights (heavy open/close)
  volume_pace(cum, elapsed, total)     projected EOD volume + pace vs a typical day
  eod_close_projection(...)            VWAP/drift projected to the close + conformal-style band
  eod_outlook(bars, ctx)               the combined panel object

A "bar" = {bucket, ret(log), vol, p(log price), price}. ctx carries the daily-history anchors
{avgDailyVol, dailyHV, openPx, totalBuckets, profile?(override)}.
"""
from __future__ import annotations
import math

BUCKETS_PER_DAY = 26          # 9:30->16:00 at 15-min
ANN = 252


def _mean(x):
    return sum(x) / len(x) if x else 0.0


def intraday_rv(returns):
    """Realized vol from 15-min log returns -> {rvDay, rvAnn}. rvDay is the sqrt of summed squared
    returns (the day's realized standard deviation so far, extrapolated to a full day)."""
    rs = [r for r in returns if r is not None]
    if not rs:
        return {"rvDay": 0.0, "rvAnn": 0.0, "n": 0}
    ss = sum(r * r for r in rs)
    rv_so_far = math.sqrt(ss)                                  # realized over the elapsed window
    per_bucket = math.sqrt(ss / len(rs)) if rs else 0.0
    rv_full = per_bucket * math.sqrt(BUCKETS_PER_DAY)          # extrapolated to a full session
    return {"rvDay": rv_full, "rvSoFar": rv_so_far, "rvAnn": rv_full * math.sqrt(ANN), "n": len(rs)}


def tod_volume_profile(n=BUCKETS_PER_DAY):
    """Normalized U-shaped intraday volume weights (heavier at the open and the close)."""
    w = []
    for i in range(n):
        edge = math.exp(-i / 4.0) + math.exp(-(n - 1 - i) / 4.0)   # open + close humps
        w.append(1.0 + 2.6 * edge)
    s = sum(w)
    return [x / s for x in w]


def volume_pace(cum_vol, elapsed, total=BUCKETS_PER_DAY, avg_daily_vol=None, profile=None):
    """Project EOD volume from the cumulative volume so far and the time-of-day profile.
    Returns projectedEOD, fracDone (typical share of a day's volume done by now), and pace
    (today's cumulative vs a typical day's cumulative by this time)."""
    prof = profile or tod_volume_profile(total)
    elapsed = max(0, min(elapsed, len(prof)))
    frac = sum(prof[:elapsed]) or 1e-9
    proj = cum_vol / frac
    pace = None
    if avg_daily_vol and avg_daily_vol > 0:
        pace = cum_vol / (avg_daily_vol * frac)               # >1 => running hotter than normal
    return {"projEodVol": proj, "fracDone": frac, "pace": pace}


def eod_close_projection(p_now_log, drift_per_bucket, sigma_per_bucket, buckets_remaining, open_px=None, z=1.6448536):
    """Project the close from the current log-price + per-bucket drift over the remaining buckets,
    with a sqrt-time band. Returns close, lo, hi and (if open given) projected day %."""
    rem = max(0, buckets_remaining)
    p_close = p_now_log + drift_per_bucket * rem
    band = z * sigma_per_bucket * math.sqrt(rem) if rem > 0 else 0.0
    close = math.exp(p_close)
    lo, hi = math.exp(p_close - band), math.exp(p_close + band)
    out = {"close": close, "lo": lo, "hi": hi}
    if open_px and open_px > 0:
        out["pctClose"] = close / open_px - 1.0
        out["pctLo"] = lo / open_px - 1.0
        out["pctHi"] = hi / open_px - 1.0
    return out


def eod_outlook(bars, ctx):
    """Combine the 15-min stream + daily history into the EOD outlook object. No look-ahead."""
    bars = [b for b in (bars or []) if b]
    if not bars:
        return None
    total = ctx.get("totalBuckets", BUCKETS_PER_DAY)
    elapsed = len(bars)
    rem = max(0, total - elapsed)
    rets = [b.get("ret", 0.0) for b in bars]
    vols = [b.get("vol", 0.0) or 0.0 for b in bars]
    prices = [b.get("price") for b in bars if b.get("price")]
    cum_vol = sum(vols)
    price_now = prices[-1] if prices else math.exp(bars[-1].get("p", 0.0))
    p_now_log = bars[-1].get("p", math.log(price_now) if price_now > 0 else 0.0)
    open_px = ctx.get("openPx") or (prices[0] if prices else price_now)

    rv = intraday_rv(rets)
    # EWMA drift + dispersion of recent 15-min returns
    lam, num, den, w = 0.85, 0.0, 0.0, 1.0
    for r in reversed(rets):
        num += w * r; den += w; w *= lam
    drift = num / den if den else 0.0
    mu = _mean(rets)
    sig = math.sqrt(sum((r - mu) ** 2 for r in rets) / max(1, len(rets) - 1)) if len(rets) > 1 else abs(mu) + 1e-6

    vp = volume_pace(cum_vol, elapsed, total, ctx.get("avgDailyVol"))
    proj = eod_close_projection(p_now_log, drift, sig, rem, open_px)
    # VWAP
    tot_v = sum(vols) or 1e-9
    vwap = sum((prices[i] if i < len(prices) else price_now) * vols[i] for i in range(len(vols))) / tot_v

    avgv = ctx.get("avgDailyVol")
    hv = ctx.get("dailyHV")                                   # annualized daily HV (decimal)
    return {
        "elapsed": elapsed, "remaining": rem, "priceNow": price_now, "vwap": vwap,
        "pctNow": (price_now / open_px - 1.0) if open_px else None,
        # volume
        "cumVol": cum_vol, "projEodVol": vp["projEodVol"], "fracDone": vp["fracDone"],
        "volPace": vp["pace"], "projRVOL": (vp["projEodVol"] / avgv) if (avgv and avgv > 0) else None,
        # volatility
        "intradayRVann": rv["rvAnn"], "dailyHVann": hv,
        "rvVsHv": (rv["rvAnn"] / hv) if (hv and hv > 0) else None,
        "volRegime": ("elevated" if (hv and rv["rvAnn"] > 1.25 * hv) else
                      ("compressed" if (hv and rv["rvAnn"] < 0.8 * hv) else "normal")),
        # close projection
        "projClose": proj["close"], "projLo": proj["lo"], "projHi": proj["hi"],
        "projPct": proj.get("pctClose"), "projPctLo": proj.get("pctLo"), "projPctHi": proj.get("pctHi"),
        "driftPerBucket": drift, "sigmaPerBucket": sig,
    }


__all__ = ["intraday_rv", "tod_volume_profile", "volume_pace", "eod_close_projection", "eod_outlook", "BUCKETS_PER_DAY"]
