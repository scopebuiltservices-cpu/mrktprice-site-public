"""Real-rate curve architecture (stdlib) — replaces the TLT proxy with the actual real Treasury curve.

Treasury's daily REAL constant-maturity table has no 2-year point (only 5/7/10/20/30), so we build the
Diebold-Li level/slope/curvature from the real 5s/10s/30s (FRED DFII5/DFII10/DFII30):
    L = (y5 + y10 + y30)/3      S = y30 - y5      C = 2*y10 - y5 - y30
and drive per-name exposure off the daily CHANGES dL,dS,dC. Per-name duration betas come from a rolling
OLS  r_i = a + bMKT*rmkt + bL*dL + bS*dS + bC*dC + e  with t-stats, then a curve-aware classification.
fetch is FRED-gated and self-skips to None without a key. Research only.
"""
import os


def lsc(y5, y10, y30):
    """Diebold-Li level/slope/curvature from the real 5/10/30 points."""
    return {"L": (y5 + y10 + y30) / 3.0, "S": y30 - y5, "C": 2.0 * y10 - y5 - y30}


def _diff(a):
    return [a[i] - a[i - 1] for i in range(1, len(a))]


def _inv(M):
    n = len(M); A = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-300: return None
        A[c], A[piv] = A[piv], A[c]
        d = A[c][c]
        for j in range(2 * n): A[c][j] /= d
        for r in range(n):
            if r == c: continue
            f = A[r][c]
            for j in range(2 * n): A[r][j] -= f * A[c][j]
    return [row[n:] for row in A]


def _ols_t(X, y):
    """OLS betas + t-stats (classical SE). Returns (beta[], t[]) or None."""
    n = len(X); p = len(X[0])
    if n <= p + 1: return None
    XtX = [[0.0] * p for _ in range(p)]; Xty = [0.0] * p
    for i in range(n):
        for a in range(p):
            Xty[a] += X[i][a] * y[i]
            for b in range(p): XtX[a][b] += X[i][a] * X[i][b]
    inv = _inv(XtX)
    if inv is None: return None
    beta = [sum(inv[a][b] * Xty[b] for b in range(p)) for a in range(p)]
    sse = 0.0
    for i in range(n):
        yh = sum(X[i][a] * beta[a] for a in range(p)); sse += (y[i] - yh) ** 2
    s2 = sse / max(1, n - p)
    t = []
    for a in range(p):
        se = (s2 * inv[a][a]) ** 0.5 if inv[a][a] > 0 else float("inf")
        t.append(beta[a] / se if se > 0 and se != float("inf") else 0.0)
    return beta, t


def duration_betas(rets, rmkt, dL, dS, dC):
    """Rolling OLS r = a + bMKT*rmkt + bL*dL + bS*dS + bC*dC. Returns {bMKT,bL,tL,bS,tS,bC,tC} or None.
    All inputs are aligned same-length daily series."""
    n = min(len(rets), len(rmkt), len(dL), len(dS), len(dC))
    if n < 30: return None
    X = [[1.0, rmkt[i], dL[i], dS[i], dC[i]] for i in range(n)]
    res = _ols_t(X, rets[:n])
    if not res: return None
    b, t = res
    return {"bMKT": round(b[1], 4), "bL": round(b[2], 3), "tL": round(t[2], 2),
            "bS": round(b[3], 3), "tS": round(t[3], 2), "bC": round(b[4], 3), "tC": round(t[4], 2)}


def classify(d, tmin=2.0):
    """Curve-aware rate classification from duration_betas output."""
    if not d: return "rate-agnostic"
    if abs(d.get("tL", 0)) >= tmin:
        return "long-duration (rate-down beneficiary)" if d["bL"] < 0 else "anti-duration (rate-up beneficiary)"
    if abs(d.get("tS", 0)) >= tmin:
        return "steepener-sensitive" if d["bS"] > 0 else "flattener-sensitive"
    if abs(d.get("tC", 0)) >= tmin:
        return "belly/curvature-sensitive"
    return "rate-agnostic"


def fetch_real_curve_history(days=160, sess=None):
    """FRED real CMT history (DFII5/DFII10/DFII30). Returns {dates,y5,y10,y30} aligned, or None.
    Self-skips without FRED_API_KEY. The 2y-real point is intentionally absent (not published)."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key: return None
    try:
        import requests, datetime, io, csv
    except Exception:
        return None
    end = datetime.date.today(); start = end - datetime.timedelta(days=days + 40)
    def series(sid):
        url = "https://api.stlouisfed.org/fred/series/observations"
        p = {"series_id": sid, "api_key": key, "file_type": "json",
             "observation_start": start.isoformat(), "observation_end": end.isoformat()}
        try:
            r = (sess or requests).get(url, params=p, timeout=30); j = r.json()
            out = {}
            for o in (j.get("observations") or []):
                v = o.get("value")
                try: out[o["date"]] = float(v)
                except Exception: pass
            return out
        except Exception:
            return {}
    a, b, c = series("DFII5"), series("DFII10"), series("DFII30")
    common = sorted(set(a) & set(b) & set(c))
    if len(common) < 30: return None
    return {"dates": common, "y5": [a[d] for d in common], "y10": [b[d] for d in common], "y30": [c[d] for d in common]}


def curve_state(hist):
    """Latest L/S/C plus the day-over-day change. hist from fetch_real_curve_history (or equivalent)."""
    if not hist or len(hist.get("dates", [])) < 2: return None
    n = len(hist["dates"])
    cur = lsc(hist["y5"][n - 1], hist["y10"][n - 1], hist["y30"][n - 1])
    prv = lsc(hist["y5"][n - 2], hist["y10"][n - 2], hist["y30"][n - 2])
    return {"L": round(cur["L"], 3), "S": round(cur["S"], 3), "C": round(cur["C"], 3),
            "dL": round(cur["L"] - prv["L"], 4), "dS": round(cur["S"] - prv["S"], 4), "dC": round(cur["C"] - prv["C"], 4),
            "asof": hist["dates"][n - 1]}


def curve_change_series(hist):
    """Aligned dL,dS,dC daily-change series for the per-name regression."""
    if not hist or len(hist.get("dates", [])) < 3: return None
    L = [lsc(hist["y5"][i], hist["y10"][i], hist["y30"][i])["L"] for i in range(len(hist["dates"]))]
    S = [lsc(hist["y5"][i], hist["y10"][i], hist["y30"][i])["S"] for i in range(len(hist["dates"]))]
    C = [lsc(hist["y5"][i], hist["y10"][i], hist["y30"][i])["C"] for i in range(len(hist["dates"]))]
    return {"dates": hist["dates"][1:], "dL": _diff(L), "dS": _diff(S), "dC": _diff(C)}
