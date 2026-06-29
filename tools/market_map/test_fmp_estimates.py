"""Offline parser tests for fmp_estimates.py (no network)."""
import datetime as dt
import fmp_estimates as FE

def test_estimates_picks_future_period():
    today = dt.date(2026, 6, 28)
    payload = [
        {"date": "2025-09-30", "estimatedRevenueAvg": 4.0e11, "estimatedEpsAvg": 6.5, "numberAnalystsEstimatedRevenue": 30},
        {"date": "2026-09-30", "estimatedRevenueAvg": 4.3e11, "estimatedEpsAvg": 7.2, "numberAnalystsEstimatedRevenue": 34},
    ]
    e = FE.parse_estimates(payload, today=today)
    assert e["fy"] == "2026-09-30" and abs(e["epsAvg"] - 7.2) < 1e-9 and e["nEst"] == 34, e

def test_surprise_recent_with_both():
    payload = [
        {"date": "2026-05-01", "epsActual": None, "epsEstimated": 1.5},      # skip (no actual)
        {"date": "2026-02-01", "epsActual": 2.20, "epsEstimated": 2.00},     # +10%
    ]
    s = FE.parse_surprise(payload)
    assert abs(s["surprisePct"] - 10.0) < 1e-9 and s["surpriseDate"] == "2026-02-01", s

def test_empty_none():
    assert FE.parse_estimates([]) is None and FE.parse_surprise([]) is None
    assert FE.parse_surprise([{"epsActual": 1, "epsEstimated": 0}]) is None   # est=0 guarded

if __name__ == "__main__":
    test_estimates_picks_future_period(); test_surprise_recent_with_both(); test_empty_none()
    print("test_fmp_estimates: 3/3 PASS")
