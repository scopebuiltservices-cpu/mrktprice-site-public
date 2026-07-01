"""Network-free test for debt_board.debt_for: planted companyfacts -> correct n['debt'] block,
mcap-key flexibility, ETF/factor skip, and idempotence of the score-relevant fields."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import debt_board as B

fail = 0


def ok(name, cond, extra=""):
    global fail
    if cond:
        print("  PASS ", name)
    else:
        print("  FAIL ", name, extra); fail = 1


def _usd(rows):
    return {"units": {"USD": rows}}


CF = {"facts": {"us-gaap": {
    "LongTermDebtNoncurrent": _usd([
        {"end": "2021-12-31", "val": 600, "fy": 2021, "fp": "FY", "form": "10-K", "filed": "2022-02-01"},
        {"end": "2022-12-31", "val": 900, "fy": 2022, "fp": "FY", "form": "10-K", "filed": "2023-02-01"},
        {"end": "2023-12-31", "val": 1000, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "LongTermDebtCurrent": _usd([
        {"end": "2023-12-31", "val": 200, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "CashAndCashEquivalentsAtCarryingValue": _usd([
        {"end": "2023-12-31", "val": 300, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "StockholdersEquity": _usd([
        {"end": "2023-12-31", "val": 400, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "InterestExpense": _usd([
        {"end": "2023-12-31", "val": 90, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "OperatingIncomeLoss": _usd([
        {"end": "2023-12-31", "val": 150, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
    "DepreciationDepletionAndAmortization": _usd([
        {"end": "2023-12-31", "val": 50, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2024-02-01"}]),
}}}

node = {"t": "TEST", "mcap": 1000}
blk = B.debt_for(node, CF)
ok("block produced", blk is not None)
ok("netDebt = 1200-300 = 900", blk["netDebt"] == 900.0, blk["netDebt"])
ok("EV = 1000+1200-300 = 1900", blk["ev"] == 1900.0, blk["ev"])
ok("netDebt/EBITDA = 4.5", abs(blk["netDebtEbitda"] - 4.5) < 1e-6, blk["netDebtEbitda"])
ok("verdict high leverage", blk["verdict"] == "high leverage", blk["verdict"])
ok("tilt in [-1,0)", blk["tilt"] is not None and -1.0 <= blk["tilt"] < 0, blk["tilt"])
ok("growth 3 levels", blk["growth"] and blk["growth"]["levels"] == 3)
ok("asOf latest fiscal end", blk["asOf"] == "2023-12-31", blk["asOf"])
ok("src stamped", "companyfacts" in blk["src"])

# mcap key flexibility
ok("reads 'marketCap' key too", B.debt_for({"t": "X", "marketCap": 1000}, CF)["ev"] == 1900.0)
ok("no mcap -> EV None but still scores leverage", B.debt_for({"t": "X"}, CF)["netDebtEbitda"] is not None)

# gating
ok("ETF skipped", B._is_equity({"t": "SPY", "etf": True}) is False)
ok("FACTOR skipped", B._is_equity({"t": "VIX", "idx": ["FACTOR"]}) is False)
ok("plain equity kept", B._is_equity({"t": "AAPL"}) is True)
ok("empty facts -> None (no signal)", B.debt_for(node, {}) is None)

# idempotence: re-running on the same inputs yields identical score-relevant fields
b2 = B.debt_for(node, CF)
ok("idempotent tilt/verdict", (b2["tilt"], b2["verdict"], b2["netDebt"]) == (blk["tilt"], blk["verdict"], blk["netDebt"]))

print("\nALL debt_board PASS" if not fail else "\nSOME debt_board TESTS FAILED")
sys.exit(1 if fail else 0)
