import sys, os, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pit_engine as P

def test_filing_deadline_tiers():
    pe = "2025-12-31"
    assert P.filing_deadline(pe, "10-K", "large") == dt.date(2026, 3, 1)   # +60
    assert P.filing_deadline(pe, "10-K", "non") == dt.date(2026, 3, 31)    # +90
    assert P.filing_deadline("2025-09-30", "10-Q", "large") == dt.date(2025, 11, 9)  # +40
    print("  PASS  filing deadlines: 10-K 60/90, 10-Q 40 days after period end")

def test_available_next_business_day():
    # filed Fri but accepted 23:00 -> next business day (Mon)
    assert P.available_at("2026-06-26", "2026-06-26T23:05:00") == dt.date(2026, 6, 29)
    # filed normally during the day -> same day
    assert P.available_at("2026-06-26", "2026-06-26T10:00:00") == dt.date(2026, 6, 26)
    print("  PASS  after-hours/weekend filing -> available next business day")

def test_leak_guard_drops_future():
    feats = [
        {"name": "rev_q3", "available_at": "2026-06-01"},     # public before decision
        {"name": "rev_q4", "available_at": "2026-07-15"},     # NOT yet public at decision
        {"name": "noprov"},                                   # missing provenance -> dropped (fail-closed)
    ]
    kept = P.leak_guard(feats, "2026-06-28")
    names = [f["name"] for f in kept]
    assert names == ["rev_q3"], names
    print("  PASS  leak_guard drops future-dated + no-provenance features (kept only rev_q3)")

def test_replay_detects_leak():
    good = [{"decision_ts": "2026-06-28", "features": [{"available_at": "2026-06-01"}]}]
    bad = [{"decision_ts": "2026-06-28", "features": [{"available_at": "2026-07-15"}]}]
    assert P.replay_ok(good) is True and P.replay_ok(bad) is False
    print("  PASS  replay_ok: clean history True; leaked-feature history False")

if __name__ == "__main__":
    test_filing_deadline_tiers(); test_available_next_business_day(); test_leak_guard_drops_future(); test_replay_detects_leak()
    print("\nALL PIT ENGINE TESTS PASSED")
