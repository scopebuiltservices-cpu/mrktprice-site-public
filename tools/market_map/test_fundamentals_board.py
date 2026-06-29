"""Planted tests for fundamentals_board.py (n.fund merge + target upside)."""
import fundamentals_board as FBd

def test_fund_for_with_upside():
    rec = {"pe": 31.2, "roe": 1.45, "targetAvg": 330.0, "rating": "A", "ratingScore": 4}
    f = FBd.fund_for(rec, 300.0)
    assert abs(f["pe"] - 31.2) < 1e-9 and f["rating"] == "A"
    assert abs(f["targetUpsidePct"] - 10.0) < 1e-9     # 330/300 - 1 = +10%

def test_fund_for_no_close_no_upside():
    f = FBd.fund_for({"pe": 10.0, "targetAvg": 50.0}, None)
    assert "targetUpsidePct" not in f and abs(f["pe"] - 10.0) < 1e-9

def test_empty_none():
    assert FBd.fund_for(None, 100.0) is None
    assert FBd.fund_for({}, 100.0) is None

if __name__ == "__main__":
    test_fund_for_with_upside(); test_fund_for_no_close_no_upside(); test_empty_none()
    print("test_fundamentals_board: 3/3 PASS")
