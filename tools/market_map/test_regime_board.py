"""Planted-structure tests for regime_board.py (per-name 2-state HMM regime)."""
import math, random
import regime_board as RB

def _prices_from_rets(rets, p0=100.0):
    p = [p0]
    for r in rets:
        p.append(p[-1] * math.exp(r))
    return p

def test_stress_tail_detected():
    random.seed(1)
    calm = [random.gauss(0.0003, 0.008) for _ in range(300)]
    stress = [random.gauss(-0.001, 0.040) for _ in range(120)]   # recent high-vol drawdown block
    reg = RB.regime_for(_prices_from_rets(calm + stress))
    assert reg["state"] == "stress" and reg["sep"] > 2, reg

def test_calm_series_not_flagged():
    # single-regime calm series: degenerate HMM split must NOT be labeled stress
    random.seed(2)
    calm = [random.gauss(0.0004, 0.007) for _ in range(420)]
    reg = RB.regime_for(_prices_from_rets(calm))
    assert reg["state"] == "calm", reg

def test_short_series_none():
    assert RB.regime_for([100, 101, 102]) is None

if __name__ == "__main__":
    test_stress_tail_detected(); test_calm_series_not_flagged(); test_short_series_none()
    print("test_regime_board: 3/3 PASS")
