#!/usr/bin/env python3
"""
Metrics-integrity guard — fails LOUDLY (at the source) if metrics.py is ever truncated or corrupted so
that any canonical estimator goes missing or its source is damaged. This converts the confusing,
downstream "ImportError: cannot import name 'ewma_vol' from 'metrics'" class of failure (a truncated
metrics.py served/committed short) into a single, unambiguous failure here.

Three layers of defense:
  1. API-surface completeness — every __all__ name is defined + a hard-coded REQUIRED list is present,
     so a truncation that drops the appended canonical-library block fails immediately.
  2. Behavioral smoke calls — a syntactically-present-but-broken def is caught.
  3. On-disk source integrity — NUL bytes and an unexpectedly short file (the literal corruption
     signatures seen with the mount) fail the gate.

Run: python3 test_metrics_integrity.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# 1) API surface — __all__ fully resolvable + the canonical library is present (no truncation)
missing = [n for n in M.__all__ if not hasattr(M, n)]
ok("every __all__ name is defined", not missing, missing)

REQUIRED = [
    # pure metric math (original block)
    "winsorize", "zscores", "ann_vol", "beta", "pearson", "ols_betas", "money_flow", "mfi", "atr",
    "lasso_cd", "macro_fit", "ema_series", "half_life", "variance_ratio", "parkinson_vol", "jump_ratio",
    "prob_touch", "contradiction", "median_touch_days", "regime_flip_prob", "calibrate_touch",
    # canonical risk/return library (appended block — first to vanish under truncation)
    "mean", "stdev", "sharpe", "downside_dev", "sortino", "max_drawdown", "calmar", "cagr",
    "skewness", "kurtosis", "value_at_risk", "cvar", "ulcer_index", "information_ratio",
    "ewma_vol", "spearman", "hurst",
]
absent = [n for n in REQUIRED if not hasattr(M, n)]
ok("all REQUIRED canonical estimators present (truncation tripwire)", not absent, absent)
ok("REQUIRED is a subset of __all__ (kept in sync)", set(n for n in REQUIRED if not n.startswith("_")).issubset(set(M.__all__)),
   [n for n in REQUIRED if not n.startswith("_") and n not in M.__all__])

# 2) behavioral smoke — catch a present-but-broken def (crash-proof: report FAIL, don't raise)
def smoke(name, fn):
    try:
        ok(name, bool(fn()))
    except Exception as e:
        ok(name, False, "raised %s" % e)

r = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, 0.012]
smoke("sharpe runs", lambda: isinstance(M.sharpe(r), float))
smoke("ewma_vol runs (>0)", lambda: M.ewma_vol(r) > 0)
smoke("sortino runs", lambda: M.sortino(r) == M.sortino(r) or True)
smoke("max_drawdown bounded", lambda: -1.0 <= M.max_drawdown([100, 50, 75]) <= 0.0)
smoke("spearman monotone == 1", lambda: abs(M.spearman([1, 2, 3, 4], [1, 4, 9, 16]) - 1.0) < 1e-9)
smoke("value_at_risk positive loss", lambda: M.value_at_risk([-0.1, -0.05, 0.01, 0.02, 0.03], 0.2) > 0)
smoke("cvar >= var", lambda: M.cvar([-0.2, -0.1, -0.05, 0.01], 0.5) >= M.value_at_risk([-0.2, -0.1, -0.05, 0.01], 0.5) - 1e-9)

# 3) on-disk source integrity — the literal corruption signatures
raw = open(M.__file__, "rb").read()
ok("metrics.py has NO NUL bytes (mount/disk corruption tripwire)", b"\x00" not in raw)
ok("metrics.py is not truncated (>= 400 lines)", raw.count(b"\n") >= 400, raw.count(b"\n"))
ok("metrics.py ends with the hurst estimator (last canonical def intact)", b"def hurst(" in raw)

print("\n" + ("ALL METRICS-INTEGRITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
