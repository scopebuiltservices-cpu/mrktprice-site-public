"""Planted-structure tests for sec_debt.py — reconstruct total debt, ignore quarterly rows, honor
restatements (latest-filed wins), and feed a clean series into debt_engine."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sec_debt as S
import debt_engine as D

fail = 0


def ok(name, cond, extra=""):
    global sys
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


def _usd(rows):
    return {"units": {"USD": rows}}


# 3 fiscal years + a quarterly row (must be ignored) + a restatement of FY2022 (latest filed wins).
CF = {"facts": {"us-gaap": {
    "LongTermDebtNoncurrent": _usd([
        {"end": "2021-12-31", "val": 600, "fy": 2021, "fp": "FY", "form": "10-K", "filed": "2022-02-01"},
        {"end": "2022-12-31", "val": 800, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01"},
        {"end": "2022-12-31", "val": 900, "fy": 2022, "fp": "FY", "form": "10-K/A", "filed": "2023-06-01"},  # restated
        {"end": "2023-12-31", "val": 1000, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"},
        {"end": "2023-09-30", "val": 950, "fy": 2023, "fp": "Q3", "form": "10-Q", "filed": "2023-10-20"},   # ignore
    ]),
    "LongTermDebtCurrent": _usd([
        {"end": "2021-12-31", "val": 50, "fy": 2021, "fp": "FY", "form": "10-K", "filed": "2022-02-01"},
        {"end": "2022-12-31", "val": 100, "fy": 2022, "fp": "FY", "form": "10-K/A", "filed": "2023-06-01"},
        {"end": "2023-12-31", "val": 200, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"},
    ]),
    "CashAndCashEquivalentsAtCarryingValue": _usd([
        {"end": "2023-12-31", "val": 300, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "ShortTermInvestments": _usd([
        {"end": "2023-12-31", "val": 50, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "StockholdersEquity": _usd([
        {"end": "2023-12-31", "val": 400, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "InterestExpense": _usd([
        {"end": "2023-12-31", "val": 90, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "OperatingIncomeLoss": _usd([
        {"end": "2023-12-31", "val": 150, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "DepreciationDepletionAndAmortization": _usd([
        {"end": "2023-12-31", "val": 50, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
}}}

ts = S.total_debt_series(CF)
ok("total-debt series values (restated FY22, no Q3)", [round(v, 1) for _, v in ts] == [650.0, 1000.0, 1200.0], ts)
ok("series is 3 fiscal years", len(ts) == 3)

snap = S.debt_snapshot(CF)
ok("latest total debt = 1200", snap["totalDebt"] == 1200.0, snap["totalDebt"])
ok("cash & STI = 350", snap["cashAndSti"] == 350.0, snap["cashAndSti"])
ok("equity 400", snap["equity"] == 400.0)
ok("interest 90", snap["interestExpense"] == 90.0)
ok("EBIT 150 / EBITDA 200", snap["ebit"] == 150.0 and snap["ebitda"] == 200.0, (snap["ebit"], snap["ebitda"]))

# end-to-end: snapshot -> debt_engine report
rep = D.debt_report(mktcap=1000, total_debt=snap["totalDebt"], cash=snap["cash"], equity=snap["equity"],
                    ebitda=snap["ebitda"], ebit=snap["ebit"], interest_expense=snap["interestExpense"],
                    debt_series=snap["debtSeries"])
ok("report EV = 1000+1200-300 = 1900", rep["ev"] == 1900.0, rep["ev"])
ok("report netDebt = 900", rep["netDebt"] == 900.0, rep["netDebt"])
ok("report netDebt/EBITDA = 4.5", abs(rep["netDebtEbitda"] - 4.5) < 1e-6, rep["netDebtEbitda"])
ok("report verdict high leverage", rep["verdict"] == "high leverage", rep["verdict"])
ok("report growth present (rising debt)", rep["growth"] and rep["growth"]["cagr"] > 0)
ok("report tilt negative (levered + rising)", rep["tilt"] is not None and rep["tilt"] < 0, rep["tilt"])

ok("empty facts -> empty series, no crash", S.total_debt_series({}) == [] and S.debt_snapshot({})["totalDebt"] is None)

print("\nALL sec_debt PASS" if not fail else "\nSOME sec_debt TESTS FAILED")
sys.exit(1 if fail else 0)
