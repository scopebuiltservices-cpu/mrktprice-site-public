"""sec_debt.py — keyless multi-period DEBT + balance-sheet pull from SEC XBRL company-facts.

Fills the "historical debt + growth" gap: SEC's companyfacts API is free (only a descriptive
User-Agent required) and exposes annual (10-K) balance-sheet + income-statement concepts, so we can
build a real multi-year total-debt series, current cash/equity, and interest expense per issuer.

Total debt is not a single US-GAAP tag, so we reconstruct it:
    total_debt = LongTermDebtNoncurrent + (LongTermDebtCurrent | DebtCurrent)
    fallback   = LongTermDebt   (already includes the current portion for many filers)

The PARSER (annual_series / total_debt_series / debt_snapshot) is pure and unit-tested against a
planted companyfacts JSON. fetch_companyfacts() is the thin network layer (defensive, self-skips).
"""
import json
from typing import Dict, List, Optional, Tuple

UA = {"User-Agent": "MrktPrice marketmap/1.0 (research; contact scopebuiltservices@gmail.com)"}

# concept -> preference order; first present wins
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
STI = ["ShortTermInvestments"]
EQUITY = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
INTEREST = ["InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense"]
EBIT = ["OperatingIncomeLoss"]
DA = ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"]
LT_NONCURRENT = ["LongTermDebtNoncurrent"]
LT_CURRENT = ["LongTermDebtCurrent"]
DEBT_CURRENT = ["DebtCurrent"]
LT_TOTAL = ["LongTermDebt"]


def _facts(cf: Dict) -> Dict:
    return ((cf or {}).get("facts", {}) or {}).get("us-gaap", {}) or {}


def annual_series(cf: Dict, concepts, unit="USD") -> List[Tuple[str, float]]:
    """Return [(fiscal_end_date, value), ...] oldest->newest for the first present concept, taking the
    annual (10-K / FY) datapoint per fiscal year (latest-filed wins on restatement)."""
    g = _facts(cf)
    rows = None
    for c in ([concepts] if isinstance(concepts, str) else concepts):
        node = g.get(c)
        if node and isinstance(node.get("units"), dict) and node["units"].get(unit):
            rows = node["units"][unit]; break
    if not rows:
        return []
    by_fy: Dict[int, Dict] = {}
    for r in rows:
        form = (r.get("form") or "")
        fp = (r.get("fp") or "")
        val = r.get("val")
        end = r.get("end")
        fy = r.get("fy")
        if val is None or end is None or fy is None:
            continue
        # annual balance-sheet / full-year points only
        if form not in ("10-K", "10-K/A", "20-F", "40-F") and fp != "FY":
            continue
        prev = by_fy.get(fy)
        if prev is None or (r.get("filed", "") >= prev.get("filed", "")):
            by_fy[fy] = {"end": end, "val": float(val), "filed": r.get("filed", "")}
    out = [(v["end"], v["val"]) for _, v in sorted(by_fy.items())]
    return out


def _latest(series: List[Tuple[str, float]]) -> Optional[float]:
    return series[-1][1] if series else None


def _sum_series(a: List[Tuple[str, float]], b: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """Add two (date,val) series by matching fiscal-end date; b is optional (missing -> 0)."""
    bd = {d: v for d, v in b}
    return [(d, v + bd.get(d, 0.0)) for d, v in a]


def total_debt_series(cf: Dict) -> List[Tuple[str, float]]:
    ltnc = annual_series(cf, LT_NONCURRENT)
    if ltnc:
        cur = annual_series(cf, LT_CURRENT) or annual_series(cf, DEBT_CURRENT)
        return _sum_series(ltnc, cur)
    return annual_series(cf, LT_TOTAL)   # fallback: single total tag


def debt_snapshot(cf: Dict) -> Dict:
    """Latest-year balance-sheet + income items + the total-debt level series (values only, oldest->newest)."""
    td = total_debt_series(cf)
    cash = annual_series(cf, CASH)
    sti = annual_series(cf, STI)
    latest_cash = _latest(cash)
    latest_sti = _latest(sti)
    cash_sti = None
    if latest_cash is not None:
        cash_sti = latest_cash + (latest_sti or 0.0)
    ebit = _latest(annual_series(cf, EBIT))
    da = _latest(annual_series(cf, DA))
    ebitda = (ebit + da) if (ebit is not None and da is not None) else None
    return {
        "totalDebt": _latest(td),
        "debtSeries": [round(v, 2) for _, v in td],
        "debtDates": [d for d, _ in td],
        "cash": latest_cash,
        "cashAndSti": cash_sti,
        "equity": _latest(annual_series(cf, EQUITY)),
        "interestExpense": _latest(annual_series(cf, INTEREST)),
        "ebit": ebit,
        "ebitda": ebitda,
    }


def fetch_companyfacts(cik: int, session=None, timeout=25) -> Optional[Dict]:
    """Thin, defensive network layer. cik is the integer CIK; SEC zero-pads to 10 digits."""
    try:
        import requests
        s = session or requests
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % int(cik)
        r = s.get(url, headers=UA, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


if __name__ == "__main__":   # tiny manual probe: python sec_debt.py 320193  (Apple)
    import sys
    if len(sys.argv) > 1:
        cf = fetch_companyfacts(int(sys.argv[1]))
        print(json.dumps(debt_snapshot(cf or {}), indent=2))
