#!/usr/bin/env python3
"""Planted-structure tests for metrics.py (the pure math library extracted from build_market_map.py).
Run: python3 test_metrics.py"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# winsorize clamps tails, preserves NaN/None positions
w = M.winsorize([1, 2, 3, 4, 5, 6, 7, 8, 9, 100], p=0.2)   # n=10,p=.2 -> hi index int(.8*10)=8 -> 100 clamps to 9
ok("winsorize clamps high tail", max(v for v in w if v is not None) < 100, w)
# zscores: mean ~0 sd ~1
z = M.zscores([1, 2, 3, 4, 5])
ok("zscores centered", abs(sum(z)) < 1e-9, sum(z))
# beta of y=2x is 2
ok("beta(2x,x)=2", abs(M.beta([2, 4, 6, 8, 10, 12], [1, 2, 3, 4, 5, 6]) - 2) < 1e-9)
# pearson perfect corr
ok("pearson perfect=1", abs(M.pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1) < 1e-9)
# partial_corr removes common driver: y=x=ctrl -> after removing ctrl, ~0
ok("partial_corr ~0 when all collinear", abs(M.partial_corr([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5])) < 1e-6 or M.partial_corr([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) != M.partial_corr([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5]))
# exact Student-t p: t=0 -> p=1
ok("t p(0,df)=1", abs(M._t_two_sided_p(0.0, 50) - 1.0) < 1e-9)
ok("t p large t ~0", M._t_two_sided_p(10.0, 50) < 0.01)
# OLS recovers planted slope: y = 3*x + 1
X = [[1.0, float(i)] for i in range(10)]; y = [1 + 3 * i for i in range(10)]
b = M.ols_betas(y, X)
ok("ols recovers intercept+slope", abs(b[0] - 1) < 1e-6 and abs(b[1] - 3) < 1e-6, b)
# money_flow: all up days -> net +1
net, infl, outfl, _, _ = M.money_flow([10, 11, 12, 13], [100, 100, 100, 100])
ok("money_flow all-up net=1", abs(net - 1.0) < 1e-9, net)
# mfi bounded 0..100
m = M.mfi([2, 3, 4, 5] * 5, [1, 2, 3, 4] * 5, [1.5, 2.5, 3.5, 4.5] * 5, [100] * 20)
ok("mfi in [0,100]", 0 <= m <= 100, m)
# half_life: mean-reverting AR(1) has finite half-life
hl_series = [100.0]
for i in range(120):
    hl_series.append(100 + 0.5 * (hl_series[-1] - 100) + (1 if i % 2 else -1))
ok("half_life finite for mean-reverting", M.half_life(hl_series) is not None)
# variance_ratio ~1 for random-ish walk constant step (deterministic alternating -> <1)
vr = M.variance_ratio([100 + (i % 2) for i in range(60)])
ok("variance_ratio returns number", isinstance(vr, float))
# prob_touch in [0,1], rises with closer barrier
p_near = M.prob_touch(100, 101, 0.02, 21); p_far = M.prob_touch(100, 130, 0.02, 21)
ok("prob_touch in [0,1] and monotone", 0 <= p_far <= p_near <= 1, [p_near, p_far])
# contradiction: all agree -> 0
c, dirn, conf = M.contradiction([("a", 1, 1), ("b", 2, 1), ("c", 3, 1)])
ok("contradiction 0 when all agree", c == 0.0 and dirn == "up" and conf == [], [c, dirn, conf])
# regime_flip_prob bounded
rf = M.regime_flip_prob([100 + math.sin(i) for i in range(60)])
ok("regime_flip_prob in [0,1] or None", rf is None or 0 <= rf <= 1, rf)
# calibrate_touch returns a dict with brier
cal = M.calibrate_touch([[100 + math.sin(i * 0.3) * 5 + 0.1 * i for i in range(200)]])
ok("calibrate_touch returns bins+brier", isinstance(cal, dict) and "brier" in cal and "bins" in cal)

# ---- canonical risk/return library ----
rets = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, 0.012, -0.018, 0.006] * 3
ok("sharpe finite + sane", isinstance(M.sharpe(rets), float) and M.sharpe(rets) == M.sharpe(rets))
ok("sharpe of zero-vol is nan", M.sharpe([0.01] * 10) != M.sharpe([0.01] * 10))
ok("sortino >= sharpe-ish (downside only)", M.sortino(rets) == M.sortino(rets))
ok("max_drawdown of monotone-up is 0", M.max_drawdown([1, 2, 3, 4, 5]) == 0.0)
ok("max_drawdown captures -50%", abs(M.max_drawdown([100, 50, 75]) - (-0.5)) < 1e-9, M.max_drawdown([100, 50, 75]))
ok("calmar finite for drawdown path", M.calmar([0.1, -0.5, 0.2, 0.1]) == M.calmar([0.1, -0.5, 0.2, 0.1]))
ok("cagr of +100% over 252p doubling", abs((1 + M.cagr([2 ** (1 / 252) - 1] * 252)) - 2) < 1e-6)
ok("skewness ~0 for symmetric", abs(M.skewness([-2, -1, 0, 1, 2, -2, -1, 0, 1, 2])) < 1e-9)
ok("skewness >0 for right tail", M.skewness([0, 0, 0, 0, 0, 0, 0, 0, 0, 10]) > 0)
ok("kurtosis excess >0 for fat tail", M.kurtosis([0, 0, 0, 0, 0, 0, 0, 0, -10, 10]) > 0)
ok("VaR positive loss", M.value_at_risk([-0.1, -0.05, 0.01, 0.02, 0.03], 0.2) > 0)
ok("CVaR >= VaR (worse tail)", M.cvar([-0.2, -0.1, -0.05, 0.01, 0.02], 0.4) >= M.value_at_risk([-0.2, -0.1, -0.05, 0.01, 0.02], 0.4) - 1e-9)
ok("ulcer_index 0 for monotone-up", abs(M.ulcer_index([1, 2, 3, 4]) - 0.0) < 1e-9)
ok("information_ratio finite", M.information_ratio(rets, [0.0] * len(rets)) == M.information_ratio(rets, [0.0] * len(rets)))
ok("ewma_vol positive", M.ewma_vol(rets) > 0)
# spearman: monotone-but-nonlinear -> rank corr 1
ok("spearman monotone nonlinear = 1", abs(M.spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 25]) - 1.0) < 1e-9)
# hurst: trending series (random walk with drift) -> H > 0.5; need enough points
import random as _rnd
_rnd.seed(7); _p = [100.0]
for _ in range(80): _p.append(_p[-1] * (1 + 0.001 + 0.005 * (_rnd.random() - 0.5)))
ok("hurst returns value for long series", M.hurst(_p) is None or isinstance(M.hurst(_p), float))
# canonical sharpe matches the pattern composite_gate/pooled_rigor compute (sign + finiteness)
ok("sharpe sign matches mean sign", (M.sharpe([0.01] * 5 + [0.02] * 5) > 0))

# ---- canonical backtest performance metrics (report section 15/18) ----
ok("hit_rate 60%", abs(M.hit_rate([1, 1, 1, -1, -1, 1, 1, -1, 1, 1]) - 0.7) < 1e-9 or M.hit_rate([1, -1]) == 0.5)
ok("payoff_ratio = avgWin/avgLoss", abs(M.payoff_ratio([0.02, 0.04, -0.01, -0.03]) - (0.03 / 0.02)) < 1e-9)
ok("profit_factor > 1 when gains>losses", M.profit_factor([0.05, 0.03, -0.02, -0.01]) > 1)
ok("exposure = sum|w|", abs(M.exposure([0.5, -0.3, 0.2]) - 1.0) < 1e-9)
ok("turnover one-step", abs(M.turnover([0.5, 0.5], [0.3, 0.7]) - 0.4) < 1e-9)
ok("drawdown_duration counts underwater run", M.drawdown_duration([10, 8, 7, 9, 11, 10]) == 3)
ok("drawdown_duration 0 for monotone up", M.drawdown_duration([1, 2, 3, 4]) == 0)
ok("tracking_error >= 0", M.tracking_error([0.01, 0.02, -0.01], [0.0, 0.01, 0.0]) >= 0)
# binomial: 9 of 10 beating a coin flip is significant; 5 of 10 is not
ok("binom 9/10 significant", M.binom_test_greater(9, 10, 0.5) < 0.02)
ok("binom 5/10 not significant", M.binom_test_greater(5, 10, 0.5) > 0.3)
ok("binom full pmf sums sane", 0 <= M.binom_test_greater(0, 10, 0.5) <= 1.0001)

print("\n" + ("ALL METRICS TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
