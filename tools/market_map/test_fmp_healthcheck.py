"""Offline tests: injected fetchers exercise each overall verdict (ok / degraded / down / no_key)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fmp_healthcheck as H

def _get_all_ok(url):
    if "commodities-list" in url or "treasury" in url or "earnings" in url or "estimates" in url:
        return 200, [{"x": 1}], 12
    if "income-statement" in url:
        return 200, [{"eps": 1.2}], 30
    if "historical-price-eod" in url:
        return 200, [{"date": "2026-06-26", "close": 200}], 40
    return 200, [{"symbol": "AAPL", "price": 200}], 11   # quote

def _get_eod_plan_blocked(url):
    if "historical-price-eod" in url:
        return 403, {"Error Message": "This endpoint is not available under your current plan"}, 20
    return _get_all_ok(url)

def _get_invalid_key(url):
    return 401, {"Error Message": "Invalid API KEY."}, 10

def _get_network_down(url):
    return 0, {"_network_error": "Connection timeout"}, 1500

def test_all_ok():
    rep = H.probe(get=_get_all_ok, key="TESTKEY")
    assert rep["overall"] == "ok" and rep["okCount"] == rep["total"], rep
    print("  PASS  all endpoints 200 -> overall=ok (%d/%d)" % (rep["okCount"], rep["total"]))

def test_eod_blocked_is_degraded():
    rep = H.probe(get=_get_eod_plan_blocked, key="TESTKEY")
    eod = next(r for r in rep["endpoints"] if r["name"] == "eod")
    assert eod["reason"] in ("plan_or_endpoint", "http_error") and not eod["ok"], eod
    assert rep["overall"] == "degraded", rep["overall"]
    assert eod.get("fix"), "missing per-endpoint fix"
    assert "KEY VALID" in rep["action"] and "plan" in rep["action"].lower(), rep["action"]
    print("  PASS  EOD plan-blocked -> degraded; self-diagnosis action: " + rep["action"][:60] + "...")

def test_invalid_key_is_down():
    rep = H.probe(get=_get_invalid_key, key="BADKEY")
    assert rep["overall"] == "down" and all(r["reason"] == "invalid_key" for r in rep["endpoints"])
    print("  PASS  invalid key -> overall=down (every endpoint invalid_key)")

def test_network_down():
    rep = H.probe(get=_get_network_down, key="TESTKEY")
    assert rep["overall"] == "down" and all(r["reason"] == "network" for r in rep["endpoints"])
    print("  PASS  network failure -> overall=down (reason=network, no crash)")

def test_no_key():
    rep = H.probe(get=_get_all_ok, key="")
    assert rep["overall"] == "no_key" and rep["key"] is False
    print("  PASS  missing key -> overall=no_key (honest)")

if __name__ == "__main__":
    test_all_ok(); test_eod_blocked_is_degraded(); test_invalid_key_is_down(); test_network_down(); test_no_key()
    print("\nALL FMP_HEALTHCHECK TESTS PASSED")
