"""Planted tests for fundamentals_board.py (n.fund merge of fundamentals + estimates + actions)."""
import fundamentals_board as FBd

def test_merge_all_sources():
    rec = {"pe": 31.2, "roe": 1.45, "targetAvg": 330.0, "rating": "A", "ratingScore": 4}
    est = {"epsAvg": 7.2, "revAvg": 4.3e11, "surprisePct": 8.5}
    act = {"div12m": 0.98, "nextExDate": "2026-08-10", "lastSplit": {"date": "2020-08-31", "ratio": "4:1"}}
    f = FBd.fund_for(rec, est, act, 300.0)
    assert abs(f["targetUpsidePct"] - 10.0) < 1e-9 and f["epsFwd"] == 7.2 and f["surprisePct"] == 8.5
    assert abs(f["div12m"] - 0.98) < 1e-9 and f["lastSplit"]["ratio"] == "4:1", f

def test_partial_sources():
    f = FBd.fund_for(None, {"epsAvg": 5.0}, None, None)
    assert f == {"epsFwd": 5.0}, f

def test_empty_none():
    assert FBd.fund_for(None, None, None, 100.0) is None

if __name__ == "__main__":
    test_merge_all_sources(); test_partial_sources(); test_empty_none()
    print("test_fundamentals_board: 3/3 PASS")
