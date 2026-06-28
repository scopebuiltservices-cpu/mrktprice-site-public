"""Real-rate curve architecture (stdlib) — replaces the TLT proxy with the actual real Treasury curve.

Treasury's daily REAL constant-maturity table has no 2-year point (only 5/7/10/20/30), so we build the
Diebold-Li level/slope/curvature from the real 5s/10s/30s (FRED DFII5/DFII10/DFII30):
    L = (y5 + y10 + y30)/3      S = y30 - y5      C = 2*y10 - y5 - y30
and drive per-name exposure off the daily CHANGES dL,dS,dC. Per-name duration betas come from a rolling
OLS  r_i = a + bMKT*rmkt + bL*dL + bS*dS + bC*dC + e  with t-stats, then a curve-aware classification.
fetch is FRED-gated and self-skips to None without a key. Research only.
"""
import os, math


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


def _valid_curve(hist):
    """Reject an implausible/short curve so a bad pull can't poison the rate layer. Treasury/FRED real
    constant-maturity yields are reported in PERCENT; a sane band is [-4, 9] %. Need >=30 aligned points."""
    if not hist or len(hist.get("dates", [])) < 30:
        return False
    for k in ("y5", "y10", "y30"):
        for v in hist.get(k, []):
            if v is None or not math.isfinite(v) or v < -4.0 or v > 9.0:
                return False
    return True


def _fred_api(days, sess):
    """FRED real CMT history via the keyed JSON API (DFII5/DFII10/DFII30)."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        return None
    try:
        import requests, datetime
    except Exception:
        return None
    end = datetime.date.today(); start = end - datetime.timedelta(days=days + 40)
    def series(sid):
        url = "https://api.stlouisfed.org/fred/series/observations"
        p = {"series_id": sid, "api_key": key, "file_type": "json",
             "observation_start": start.isoformat(), "observation_end": end.isoformat()}
        try:
            r = (sess or requests).get(url, params=p, timeout=30); j = r.json(); out = {}
            for o in (j.get("observations") or []):
                try: out[o["date"]] = float(o.get("value"))
                except Exception: pass
            return out
        except Exception:
            return {}
    a, b, c = series("DFII5"), series("DFII10"), series("DFII30")
    common = sorted(set(a) & set(b) & set(c))
    if len(common) < 30:
        return None
    return {"dates": common, "y5": [a[d] for d in common], "y10": [b[d] for d in common],
            "y30": [c[d] for d in common], "source": "FRED API (DFII5/10/30)"}


def _parse_fred_csv(text):
    """fredgraph.csv -> {date:{DFII5,DFII10,DFII30}} keeping only fully-populated rows ('.' = missing)."""
    import csv, io
    out = {}; rdr = csv.reader(io.StringIO(text)); hdr = next(rdr, None)
    if not hdr:
        return out
    idx = {h.strip().upper(): i for i, h in enumerate(hdr)}; di = idx.get("DATE", 0)
    for row in rdr:
        if not row or len(row) <= di:
            continue
        d = row[di].strip(); rec = {}
        for sid in ("DFII5", "DFII10", "DFII30"):
            i = idx.get(sid)
            if i is not None and i < len(row):
                try: rec[sid] = float(row[i])
                except Exception: pass
        if d and len(rec) == 3:
            out[d] = rec
    return out


def fetch_real_curve_csv(days=160, sess=None):
    """KEYLESS official St. Louis Fed CSV (fredgraph.csv) — works with no API key."""
    try:
        import requests, datetime
    except Exception:
        return None
    end = datetime.date.today(); start = end - datetime.timedelta(days=days + 40)
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII5,DFII10,DFII30"
           "&cosd=%s&coed=%s" % (start.isoformat(), end.isoformat()))
    try:
        r = (sess or requests).get(url, timeout=30)
        if r.status_code != 200:
            return None
        rows = _parse_fred_csv(r.text)
    except Exception:
        return None
    common = sorted(rows)
    if len(common) < 30:
        return None
    return {"dates": common, "y5": [rows[d]["DFII5"] for d in common], "y10": [rows[d]["DFII10"] for d in common],
            "y30": [rows[d]["DFII30"] for d in common], "source": "FRED CSV keyless (DFII5/10/30)"}


def _parse_treasury_real(text):
    """US Treasury daily REAL par yield CSV -> {date:{5,10,30}} (columns like '5 YR','10 YR','30 YR')."""
    import csv, io
    out = {}; rdr = csv.reader(io.StringIO(text)); hdr = next(rdr, None)
    if not hdr:
        return out
    cols = {h.strip().upper(): i for i, h in enumerate(hdr)}; di = cols.get("DATE", 0)
    def col(*names):
        for nm in names:
            if nm in cols: return cols[nm]
        return None
    i5 = col("5 YR", "5YR"); i10 = col("10 YR", "10YR"); i30 = col("30 YR", "30YR")
    if None in (i5, i10, i30):
        return out
    for row in rdr:
        if not row or len(row) <= max(i5, i10, i30):
            continue
        try:
            out[row[di].strip()] = {5: float(row[i5]), 10: float(row[i10]), 30: float(row[i30])}
        except Exception:
            pass
    return out


def fetch_real_curve_treasury(days=160, sess=None):
    """Authoritative US Treasury daily REAL par yield curve (5/10/30) — the PDF's cited primary source."""
    try:
        import requests, datetime
    except Exception:
        return None
    yr = datetime.date.today().year
    base = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/%d/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=%d")
    rows = {}
    for y in (yr, yr - 1):
        try:
            r = (sess or requests).get(base % (y, y), timeout=30)
            if r.status_code == 200:
                rows.update(_parse_treasury_real(r.text))
        except Exception:
            pass
    common = sorted(rows)
    if len(common) < 30:
        return None
    common = common[-(days + 40):]
    return {"dates": common, "y5": [rows[d][5] for d in common], "y10": [rows[d][10] for d in common],
            "y30": [rows[d][30] for d in common], "source": "US Treasury real par curve (5/10/30)"}


def fetch_real_curve_history(days=160, sess=None):
    """CREDIBLE multi-source real curve with graceful failover:
        FRED API (keyed) -> FRED CSV (keyless) -> US Treasury (authoritative).
    Each candidate is validated (finite, plausible yield band, >=30 aligned points) before acceptance, and
    the winner carries hist['source']. Returns None only if every official source fails — never a bad curve."""
    for fn in (_fred_api, fetch_real_curve_csv, fetch_real_curve_treasury):
        try:
            h = fn(days, sess)
        except Exception:
            h = None
        if h and _valid_curve(h):
            return h
    return None


def curve_state(hist):
    """Latest L/S/C plus the day-over-day change. hist from fetch_real_curve_history (or equivalent)."""
    if not hist or len(hist.get("dates", [])) < 2: return None
    n = len(hist["dates"])
    cur = lsc(hist["y5"][n - 1], hist["y10"][n - 1], hist["y30"][n - 1])
    prv = lsc(hist["y5"][n - 2], hist["y10"][n - 2], hist["y30"][n - 2])
    return {"L": round(cur["L"], 3), "S": round(cur["S"], 3), "C": round(cur["C"], 3),
            "dL": round(cur["L"] - prv["L"], 4), "dS": round(cur["S"] - prv["S"], 4), "dC": round(cur["C"] - prv["C"], 4),
            "asof": hist["dates"][n - 1]}


def _lr(c):
    c = [x for x in (c or []) if x and x > 0]
    return [c[i] / c[i - 1] - 1.0 for i in range(1, len(c))]


def attach_duration_betas(names, hist, mkt_ticker="SPY", is_etf=None, tmin=2.0):
    """Per-name real-rate duration betas + classification, tail-aligned to the curve change series, written
    to n['rate']={bMKT,bL,tL,bS,tS,bC,tC,class}. Tail-alignment assumes each name's closes and the curve
    changes end on the same recent session (true for a nightly universe build). Returns count attached."""
    cs = curve_change_series(hist)
    if not cs: return 0
    dL, dS, dC = cs["dL"], cs["dS"], cs["dC"]
    rmkt = None
    for n in names:
        if (n.get("t") or "").upper() == mkt_ticker:
            rmkt = _lr(n.get("_cl") or []); break
    cnt = 0
    for n in names:
        t = (n.get("t") or "").upper()
        if not t or (is_etf and is_etf(t)): continue
        rets = _lr(n.get("_cl") or [])
        if len(rets) < 30: continue
        L = min(len(rets), len(dL), len(dS), len(dC), (len(rmkt) if rmkt else len(rets)))
        if L < 30: continue
        rk = rmkt[-L:] if rmkt else [0.0] * L
        d = duration_betas(rets[-L:], rk, dL[-L:], dS[-L:], dC[-L:])
        if not d: continue
        d["class"] = classify(d, tmin); n["rate"] = d; cnt += 1
    return cnt


def curve_change_series(hist):
    """Aligned dL,dS,dC daily-change series for the per-name regression."""
    if not hist or len(hist.get("dates", [])) < 3: return None
    L = [lsc(hist["y5"][i], hist["y10"][i], hist["y30"][i])["L"] for i in range(len(hist["dates"]))]
    S = [lsc(hist["y5"][i], hist["y10"][i], hist["y30"][i])["S"] for i in range(len(hist["dates"]))]
    C = [lsc(hist["y5"][i], hist["y10"][i], hist["y30"][i])["C"] for i in range(len(hist["dates"]))]
    return {"dates": hist["dates"][1:], "dL": _diff(L), "dS": _diff(S), "dC": _diff(C)}
