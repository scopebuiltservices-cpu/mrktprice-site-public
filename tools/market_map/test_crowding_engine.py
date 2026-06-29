import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crowding_engine as C

def test_days_to_cover():
    assert C.days_to_cover(10_000_000, 2_000_000) == 5.0 and C.days_to_cover(1, 0) is None
    print("  PASS  days-to-cover = short shares / ADV (5.0)")

def test_hhi_concentration():
    assert abs(C.ownership_hhi([100, 100, 100, 100]) - 0.25) < 1e-9      # 4 equal holders -> 1/4
    assert C.ownership_hhi([900, 100]) > C.ownership_hhi([500, 500])     # concentrated > even
    print("  PASS  ownership HHI: 4 equal->0.25; concentrated>even")

def test_util_fee_convex():
    assert C.utilization_proxy_fee(0.2) < 1.0 and C.utilization_proxy_fee(1.0) > 9.0
    assert C.utilization_proxy_fee(0.95) > C.utilization_proxy_fee(0.8)
    print("  PASS  utilization->fee convex (0.2->%.2f%%, 1.0->%.2f%%)" % (C.utilization_proxy_fee(0.2), C.utilization_proxy_fee(1.0)))

def test_penalty_and_short_net():
    p_lo = C.crowding_penalty(0.02, 0.1, 0.3)
    p_hi = C.crowding_penalty(0.25, 0.6, 0.95)        # heavily shorted + concentrated + utilized
    assert p_hi > p_lo >= 0
    # short thesis net of a 10% borrow fee over a quarter
    assert C.short_net_mu(3.0, 10.0, 0.0, 0.25) < 3.0
    print("  PASS  crowding penalty rises with SI/HHI/util (%.3f -> %.3f); short net-of-borrow applied" % (p_lo, p_hi))

if __name__ == "__main__":
    test_days_to_cover(); test_hhi_concentration(); test_util_fee_convex(); test_penalty_and_short_net()
    print("\nALL CROWDING ENGINE TESTS PASSED")
