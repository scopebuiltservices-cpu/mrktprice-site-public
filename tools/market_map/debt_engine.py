"""debt_engine.py — leverage / credit metrics + a bounded leverage tilt for the board.

Pure stdlib, keyless. Inputs are already-pulled fundamentals (total debt, cash, equity, EBITDA,
EBIT, interest expense, market cap) plus an optional multi-period total-debt series for growth.
Every function returns None on missing/degenerate input (matches the codebase's defensive style),
so a name with partial data still scores on what IS present.

Metrics:
  net_debt            = total_debt - cash_and_sti
  enterprise_value    = mktcap + total_debt + preferred + minority_interest - cash
  ev_ebitda           = EV / EBITDA                 (valuation, leverage-adjusted)
  net_debt_to_ebitda  = net_debt / EBITDA           (credit: how many years of EBITDA to repay)
  debt_to_equity      = total_debt / equity
  interest_coverage   = EBIT / interest_expense     (credit: can it service the debt?)
  debt_growth         = period-over-period % change of total debt + trailing CAGR

leverage_tilt() folds the credit picture into a single bounded score in [-1, +1]:
  positive  = net cash / low leverage / strong coverage / deleveraging  -> supportive of the name
  negative  = high net-debt/EBITDA / weak coverage / rapid debt growth  -> a headwind
It is deliberately bounded and monotone so the board can scale it into the expected-return number
without letting one noisy input dominate.
"""
from typing import Optional, Sequence, List, Dict


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        return v if v == v else None   # drop NaN
    except (TypeError, ValueError):
        return None


def net_debt(total_debt, cash_and_sti) -> Optional[float]:
    td, c = _num(total_debt), _num(cash_and_sti)
    if td is None or c is None:
        return None
    return td - c


def enterprise_value(mktcap, total_debt, cash_and_sti, preferred=0.0, minority_interest=0.0) -> Optional[float]:
    mc, td, c = _num(mktcap), _num(total_debt), _num(cash_and_sti)
    if mc is None or td is None or c is None:
        return None
    pf = _num(preferred) or 0.0
    nci = _num(minority_interest) or 0.0
    return mc + td + pf + nci - c


def _ratio(num, den, cap=None) -> Optional[float]:
    n, d = _num(num), _num(den)
    if n is None or d is None or d == 0:
        return None
    r = n / d
    if cap is not None:
        r = max(-cap, min(cap, r))
    return r


def ev_ebitda(ev, ebitda) -> Optional[float]:
    # EBITDA <= 0 makes the multiple meaningless -> None
    e = _num(ebitda)
    if e is None or e <= 0:
        return None
    return _ratio(ev, e, cap=200.0)


def net_debt_to_ebitda(nd, ebitda) -> Optional[float]:
    e = _num(ebitda)
    if e is None or e <= 0:
        return None
    return _ratio(nd, e, cap=50.0)


def debt_to_equity(total_debt, equity) -> Optional[float]:
    eq = _num(equity)
    if eq is None or eq <= 0:      # negative book equity -> D/E undefined/uninformative
        return None
    return _ratio(total_debt, eq, cap=50.0)


def interest_coverage(ebit, interest_expense) -> Optional[float]:
    ie = _num(interest_expense)
    if ie is None:
        return None
    ie = abs(ie)                   # interest expense is sometimes signed negative
    if ie == 0:
        return None                # no interest burden -> coverage undefined (treated as net-cash elsewhere)
    e = _num(ebit)
    if e is None:
        return None
    return max(-100.0, min(100.0, e / ie))


def debt_growth(debt_series: Sequence) -> Optional[Dict]:
    """debt_series oldest->newest total-debt levels. Returns period %chg list + trailing CAGR-per-step
    + the latest step change. Needs >=2 positive points."""
    s = [_num(x) for x in (debt_series or [])]
    s = [x for x in s if x is not None and x > 0]
    if len(s) < 2:
        return None
    chg = [(s[i] / s[i - 1] - 1.0) for i in range(1, len(s))]
    steps = len(s) - 1
    cagr = (s[-1] / s[0]) ** (1.0 / steps) - 1.0
    return {"pct": [round(c, 4) for c in chg], "last": round(chg[-1], 4),
            "cagr": round(cagr, 4), "levels": len(s)}


def _clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def leverage_tilt(nd_ebitda: Optional[float], coverage: Optional[float],
                  growth: Optional[Dict], is_net_cash: bool = False) -> Optional[float]:
    """Bounded credit tilt in [-1, +1]. Combines three sub-scores with fixed weights; ignores
    missing components and renormalizes so a name with partial data still gets a proportional read."""
    parts, wts = [], []

    if is_net_cash:
        parts.append(1.0); wts.append(0.45)          # net cash is a clean positive
    elif nd_ebitda is not None:
        # 0x -> +1, ~2x neutral, >=6x -> -1  (piecewise-linear, capped)
        s = _clip((2.0 - nd_ebitda) / 4.0)
        parts.append(s); wts.append(0.45)

    if coverage is not None:
        # <1x can't cover -> -1; ~4x neutral; >=10x -> +1
        s = _clip((coverage - 4.0) / 6.0)
        parts.append(s); wts.append(0.35)

    if growth is not None and growth.get("cagr") is not None:
        g = growth["cagr"]
        # deleveraging (g<0) supportive; +20%/step debt growth -> -1
        s = _clip(-g / 0.20)
        parts.append(s); wts.append(0.20)

    if not parts:
        return None
    tw = sum(wts)
    return round(sum(p * w for p, w in zip(parts, wts)) / tw, 4)


def debt_report(mktcap=None, total_debt=None, cash=None, equity=None,
                ebitda=None, ebit=None, interest_expense=None,
                preferred=0.0, minority_interest=0.0, debt_series=None) -> Dict:
    """One-call bundle for the n.debt payload block."""
    nd = net_debt(total_debt, cash)
    ev = enterprise_value(mktcap, total_debt, cash, preferred, minority_interest)
    is_net_cash = (nd is not None and nd < 0)
    evb = ev_ebitda(ev, ebitda)
    nde = net_debt_to_ebitda(nd, ebitda)
    de = debt_to_equity(total_debt, equity)
    ic = interest_coverage(ebit, interest_expense)
    gr = debt_growth(debt_series) if debt_series else None
    tilt = leverage_tilt(nde, ic, gr, is_net_cash=is_net_cash)

    if is_net_cash:
        verdict = "net cash"
    elif nde is not None and nde >= 4.0:
        verdict = "high leverage"
    elif nde is not None and nde <= 1.5:
        verdict = "low leverage"
    elif de is not None and de >= 2.0:
        verdict = "elevated D/E"
    else:
        verdict = "moderate" if (nde is not None or de is not None) else "insufficient data"

    return {
        "netDebt": None if nd is None else round(nd, 2),
        "ev": None if ev is None else round(ev, 2),
        "evEbitda": evb, "netDebtEbitda": nde, "debtEquity": de, "coverage": ic,
        "netCash": is_net_cash, "growth": gr, "tilt": tilt, "verdict": verdict,
    }
