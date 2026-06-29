"""crowding_engine.py — crowding / shortability penalty (PDF 1 #11). Names that are heavily shorted,
concentrated in few holders, or hard/expensive to borrow carry extra risk; subtract a penalty from mu.
Keyless inputs: FINRA short interest (free biweekly), 13F ownership concentration (already in flow_keyless).
Borrow FEE is the one genuinely paid signal -> proxied from utilization until a lending vendor is added.
Pure stdlib; verified. Research only, not advice."""
import math

__all__ = ["crowding_penalty", "short_net_mu", "utilization_proxy_fee", "days_to_cover", "ownership_hhi"]


def days_to_cover(short_shares, avg_daily_vol):
    """Short interest ratio = shares short / ADV. Higher = more crowded / squeeze-prone."""
    if avg_daily_vol <= 0:
        return None
    return short_shares / avg_daily_vol


def ownership_hhi(holder_shares):
    """Herfindahl concentration of 13F holders: sum of squared share-fractions in [1/N, 1]. Higher = more
    concentrated (crowded into few hands)."""
    tot = sum(holder_shares) or 0.0
    if tot <= 0:
        return 0.0
    return sum((s / tot) ** 2 for s in holder_shares)


def utilization_proxy_fee(utilization):
    """Proxy annual borrow fee (%) from lending utilization in [0,1] until a paid feed exists. Convex:
    cheap below ~80% utilized, steepening into 'special' territory."""
    u = max(0.0, min(1.0, utilization))
    return 0.3 + 9.7 * (u ** 4)        # ~0.3% general collateral -> ~10% when fully utilized


def crowding_penalty(short_interest_pct, ownership_conc, utilization, a=0.6, b=0.4, c=0.5):
    """Penalty (in expected-return % terms) to SUBTRACT from mu. Inputs:
       short_interest_pct: shares short / float (0..1+), ownership_conc: HHI (0..1), utilization: 0..1."""
    si = max(0.0, short_interest_pct)
    pen = a * si + b * ownership_conc + c * max(0.0, utilization - 0.5)
    return max(0.0, pen)


def short_net_mu(mu, borrow_fee_pct, recall_penalty=0.0, horizon_frac=1.0):
    """For a SHORT thesis: net mu after borrow cost over the holding fraction of a year + recall risk."""
    return mu - (borrow_fee_pct / 100.0) * horizon_frac - recall_penalty
