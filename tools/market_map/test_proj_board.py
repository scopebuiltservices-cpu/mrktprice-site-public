"""Planted-structure tests for proj_board.py (no-lookahead forward projection + P(up))."""
import math
import proj_board as PB

def _series(drift, sd, n=300, p0=100.0, seed=7):
    import random; random.seed(seed)
    p=[p0]
    for _ in range(n): p.append(p[-1]*math.exp(random.gauss(drift,sd)))
    return p

def test_structure_and_invariant():
    pj=PB.proj_for(_series(0.0006,0.01))
    assert pj is not None and pj["h"]==21
    assert 0.0 < pj["probUp"] < 1.0 and pj["sigmaHPct"]>0
    # invariant: projPct>0 <=> probUp>0.5 (both driven by mu_H)
    assert (pj["projPct"]>0) == (pj["probUp"]>0.5), pj

def test_flat_series_near_half():
    pj=PB.proj_for(_series(0.0,0.012))
    assert 0.20 < pj["probUp"] < 0.80, pj   # no EXTREME edge (OU may mean-revert a chance drift)

def test_short_series_none():
    assert PB.proj_for([100,101,102]) is None

if __name__=="__main__":
    test_structure_and_invariant(); test_flat_series_near_half(); test_short_series_none()
    print("test_proj_board: 3/3 PASS")
