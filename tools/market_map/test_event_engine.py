"""Planted tests: market-model CAR recovers an injected abnormal jump; intensity decays; severity ranks;
stake + insider signs; eventTilt bounded and monotone."""
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_engine as E

def test_car_detects_injected_jump():
    rng = random.Random(1); T = 260
    rm = [rng.gauss(0, 0.01) for _ in range(T)]
    beta_true = 1.3
    ri = [0.0002 + beta_true * rm[t] + rng.gauss(0, 0.004) for t in range(T)]
    ev = 250
    ri[ev] += 0.06                      # +6% abnormal jump on the event day
    ar, sigma, a, b = E.abnormal_returns(ri, rm, ev - 200, ev - 10, ev, ev + 1)
    c = E.car(ar); sc = E.scar(ar, sigma)
    assert abs(b - beta_true) < 0.15, b
    assert c > 0.045, c                 # CAR captures most of the +6% jump
    assert sc > 3.0, sc                 # highly significant
    print("  PASS  market-model CAR recovers injected +6%% jump (beta=%.2f, CAR=%.3f, SCAR=%.1f)" % (b, c, sc))

def test_no_event_car_insignificant():
    rng = random.Random(2); T = 260
    rm = [rng.gauss(0, 0.01) for _ in range(T)]
    ri = [1.1 * rm[t] + rng.gauss(0, 0.004) for t in range(T)]
    ar, sigma, a, b = E.abnormal_returns(ri, rm, 50, 240, 250, 251)
    assert abs(E.scar(ar, sigma)) < 2.5
    print("  PASS  no-event window -> |SCAR| < 2.5 (no false positive)")

def test_intensity_decay():
    ev = [(0, 0.9), (5, 0.5)]
    i_now = E.event_intensity(ev, 5, tau=10)
    i_later = E.event_intensity(ev, 25, tau=10)
    assert i_now > i_later > 0
    # exact: at t=5 -> 0.9*e^-0.5 + 0.5
    assert abs(i_now - (0.9 * math.exp(-0.5) + 0.5)) < 1e-9
    print("  PASS  event intensity decays (I@5=%.3f > I@25=%.3f)" % (i_now, i_later))

def test_severity_ranks():
    assert E.eightk_severity(["4.02"]) > E.eightk_severity(["8.01"])       # restatement >> other
    assert E.eightk_severity(["1.03"]) > E.eightk_severity(["5.03"])       # bankruptcy >> bylaws
    assert E.eightk_severity(["2.02", "8.01"]) == E.EIGHTK_SEVERITY["2.02"]  # max over items
    assert E.eightk_severity(["9.99"]) == 0.25                              # unknown -> floor
    print("  PASS  8-K item severity ranks (restatement/bankruptcy high, other low, max-over-items)")

def test_stake_and_insider_signs():
    assert E.stake_signal("13D", +3.0, True) > E.stake_signal("13G", +3.0, True)   # activist > passive
    assert E.stake_signal("13D", -3.0, False) < 0                                   # stake cut -> negative
    assert E.insider_net(100, 0, 0) > 0.999 and E.insider_net(0, 100, 0) < 0
    # planned sells hurt less than discretionary
    assert E.insider_net(0, 0, 100) > E.insider_net(0, 100, 0)
    print("  PASS  stake (13D>13G, cut<0) + insider net (buy=+1, plan-sell less negative than disc-sell)")

def test_event_tilt_bounded_monotone():
    lo = E.event_tilt(-0.2, 0, -1, -1)
    hi = E.event_tilt(+0.2, 3, +1, +1)
    assert -3.0 <= lo < 0 < hi <= 3.0
    # monotone in CAR
    assert E.event_tilt(0.05, 1, 0, 0) > E.event_tilt(-0.05, 1, 0, 0)
    print("  PASS  eventTilt bounded to ±3%% and monotone in CAR (lo=%.2f hi=%.2f)" % (lo, hi))

if __name__ == "__main__":
    test_car_detects_injected_jump(); test_no_event_car_insignificant(); test_intensity_decay()
    test_severity_ranks(); test_stake_and_insider_signs(); test_event_tilt_bounded_monotone()
    print("\nALL EVENT ENGINE TESTS PASSED")
