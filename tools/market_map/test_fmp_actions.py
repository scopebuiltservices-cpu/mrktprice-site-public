"""Offline parser tests for fmp_actions.py (no network)."""
import datetime as dt
import fmp_actions as FA

def test_dividends_ttm_and_next():
    today = dt.date(2026, 6, 28)
    payload = [
        {"date": "2026-08-10", "dividend": 0.26},   # future -> next ex-date
        {"date": "2026-05-10", "dividend": 0.25},   # in TTM
        {"date": "2026-02-10", "dividend": 0.25},   # in TTM
        {"date": "2025-11-10", "dividend": 0.24},   # in TTM
        {"date": "2025-08-10", "dividend": 0.24},   # in TTM (just inside 365d)
        {"date": "2024-01-10", "dividend": 0.20},   # old -> excluded
    ]
    d = FA.parse_dividends(payload, today=today)
    assert abs(d["div12m"] - (0.25+0.25+0.24+0.24)) < 1e-9 and d["nextExDate"] == "2026-08-10", d

def test_splits_latest():
    payload = [{"date": "2020-08-31", "numerator": 4, "denominator": 1},
               {"date": "2014-06-09", "numerator": 7, "denominator": 1}]
    s = FA.parse_splits(payload)
    assert s["date"] == "2020-08-31" and s["ratio"] == "4:1", s

def test_empty_none():
    assert FA.parse_dividends([]) is None and FA.parse_splits([]) is None

if __name__ == "__main__":
    test_dividends_ttm_and_next(); test_splits_latest(); test_empty_none()
    print("test_fmp_actions: 3/3 PASS")
