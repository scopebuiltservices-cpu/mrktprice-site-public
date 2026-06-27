"""Walk-forward threshold fitter for the intraday conviction gate (stdlib).

Given accumulated {metric_value, forward_return} trigger outcomes, fits the cutoff that maximizes the
post-trigger forward-return t-stat (min-hit gated), evaluated OUT OF SAMPLE on a holdout, and reports an
HONEST trial count for the composite's deflated-Sharpe accounting. Until enough outcomes accrue, callers
keep the literature defaults (RVOL 2.0, |z| 2.0, OBV |t| 2.0, ...). Mirrors the est/ic snapshot discipline:
the cutoffs strengthen as the trigger-outcome history grows. Research only.
"""
import math, datetime


def _mean_t(xs):
    n = len(xs)
    if n < 2: return 0.0, 0.0
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    se = math.sqrt(v / n) if v > 0 else 0.0
    return m, (m / se if se > 0 else 0.0)


def fit_cutoff(values, fwd, grid, min_hits=20, side="ge"):
    """Best cutoff over `grid` maximizing |t| of forward returns among events that pass
    (value>=θ for side 'ge', value<=θ for 'le'), subject to >= min_hits. Returns {theta,t,mean,n} or None."""
    best = None
    for th in grid:
        sel = [fwd[i] for i in range(min(len(values), len(fwd)))
               if (values[i] >= th if side == "ge" else values[i] <= th)]
        if len(sel) < min_hits: continue
        m, t = _mean_t(sel)
        if best is None or abs(t) > abs(best["t"]):
            best = {"theta": th, "t": round(t, 3), "mean": round(m, 5), "n": len(sel)}
    return best


def walk_forward(values, fwd, grid, train_frac=0.6, min_hits=20, side="ge"):
    """Fit θ on the train split; evaluate its forward-return t-stat OUT OF SAMPLE on the holdout.
    Returns {theta,tIS,tOOS,meanOOS,nTest,trials} or None. trials = configurations evaluated (= len(grid))."""
    n = min(len(values), len(fwd))
    if n < 3 * min_hits: return None
    k = int(n * train_frac)
    fit = fit_cutoff(values[:k], fwd[:k], grid, min_hits, side)
    if not fit: return None
    th = fit["theta"]
    test = [fwd[i] for i in range(k, n) if (values[i] >= th if side == "ge" else values[i] <= th)]
    if len(test) < max(5, min_hits // 2): return None
    m, t = _mean_t(test)
    return {"theta": th, "tIS": fit["t"], "tOOS": round(t, 3), "meanOOS": round(m, 5),
            "nTest": len(test), "trials": len(grid)}


def calibrate(metrics, defaults, asof=None, train_window=None, min_toos=1.0):
    """metrics: {name:{values,fwd,grid,side,min_hits}}. Returns an alpha_calib-style block: per-metric
    fitted cutoff (or labeled default when the OOS t-stat is too weak / data too thin) plus the TOTAL trial
    count that the composite's DSR must charge for."""
    asof = asof or datetime.date.today().isoformat()
    out = {"asof": asof, "trainWindow": train_window, "cutoffs": {}, "mode": {}, "tOOS": {}, "trials": 0}
    for name, m in metrics.items():
        grid = m.get("grid", []) or []
        wf = walk_forward(m.get("values", []), m.get("fwd", []), grid,
                          min_hits=m.get("min_hits", 20), side=m.get("side", "ge"))
        if wf and wf["tOOS"] >= min_toos:
            out["cutoffs"][name] = wf["theta"]; out["mode"][name] = "fitted"; out["tOOS"][name] = wf["tOOS"]
        else:
            out["cutoffs"][name] = defaults.get(name); out["mode"][name] = "default"
            out["tOOS"][name] = (wf["tOOS"] if wf else None)
        out["trials"] += len(grid)            # every cutoff tried counts as a trial for DSR honesty
    return out
