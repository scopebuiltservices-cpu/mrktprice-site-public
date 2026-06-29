"""Planted tests for sector_reconcile.py (authoritative sector + mismatch flag + ETF protection)."""
import sector_reconcile as SR

def test_corrects_mismatch_and_flags():
    mm = {"names": [
        {"t": "JPM", "sec": "Technology"},                 # wrong self-label -> corrected + flagged
        {"t": "AAPL", "sec": "Technology"},                # already right -> no mismatch
        {"t": "USO", "sec": "Commodity"},                  # ETF bucket -> untouched (no profile sector)
    ]}
    prof = {"JPM": {"sector": "Financials"}, "AAPL": {"sector": "Technology"}, "USO": {"sector": None}}
    done, mism = SR.enrich(mm, prof)
    by = {n["t"]: n for n in mm["names"]}
    assert done == 2 and mism == 1
    assert by["JPM"]["sec"] == "Financials" and by["JPM"]["secOrig"] == "Technology" and by["JPM"]["secMismatch"] is True
    assert by["AAPL"]["sec"] == "Technology" and by["AAPL"]["secMismatch"] is False
    assert by["USO"]["sec"] == "Commodity" and "secAuth" not in by["USO"]   # ETF untouched

if __name__ == "__main__":
    test_corrects_mismatch_and_flags()
    print("test_sector_reconcile: 1/1 PASS")
