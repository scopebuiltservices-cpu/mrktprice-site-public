#!/usr/bin/env python3
"""monitoring.py — continuous calibration & drift monitor (keyless, self-data). Closes the loop:
reads the board's OWN nightly logs and emits monitoring/latest.json with calibration / drift / skill
metrics and alert flags. No external feed.

Inputs (all optional; each metric degrades to None if its log is missing/too short):
  data/alpha_log.jsonl   rows {"d":asof,"t":ticker,"alpha":pred,"px":..,"fwd":realized_return}   (alpha_calib.py)
  health_log.jsonl       rows {asof, dataQuality:{clean,degraded,reject}, fmpDegraded, driftCensus:{significant,..}}
  data/factor_ic.jsonl   rows {origin, asof, h, n, ic:{factor:val}}                               (ic_store.py)

Metrics:
  rankIC / IC      Spearman & Pearson of predicted alpha vs realized fwd (overall + recent window)
  hitRate          sign-agreement of predicted vs realized (skill > 0.5)
  decileMonotonic  Spearman(decile index, mean realized) over alpha deciles (monotone payoff = 1.0)
  spreadDSR        Deflated Sharpe (Bailey-LdP) of the per-period top-minus-bottom-decile return series
  alphaPSI         Population Stability Index of the predicted-alpha distribution, recent vs prior window
  health           degraded-fraction, fmp-degraded streak, drift-significant fraction over recent builds
Alerts fire only on computable metrics. Overall status = max severity (ok < warn < alert).

CLI: python3 monitoring.py [--root .] [--out monitoring/latest.json] [--window 10] [--horizon 21]
Exit 0 always (monitoring never fails the build); --strict makes any 'alert' exit 2."""
import argparse, json, math, os, sys, datetime as dt

# ---- reuse the verified DSR; degrade gracefully if not importable ----
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from factor_eval import deflated_sharpe as _dsr
except Exception:
    _dsr = None


def _read_jsonl(path):
    rows = []
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    return rows


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _spearman(xs, ys):
    if len(xs) < 3:
        return None
    return _pearson(_rank(xs), _rank(ys))


def _quantile_buckets(pairs, q=10):
    """pairs=[(pred,real)] sorted by pred, split into q near-equal buckets -> list of (idx, mean_real)."""
    if len(pairs) < q:
        q = max(2, len(pairs) // 3)
    if q < 2 or len(pairs) < q:
        return None
    s = sorted(pairs, key=lambda p: p[0])
    out = []
    n = len(s)
    for b in range(q):
        lo = b * n // q; hi = (b + 1) * n // q
        seg = s[lo:hi]
        if not seg:
            return None
        out.append((b, sum(p[1] for p in seg) / len(seg)))
    return out


def _psi(expected, actual, bins=10):
    """Population Stability Index of two samples using quantile bin edges from `expected`."""
    if len(expected) < bins or len(actual) < bins:
        return None
    e = sorted(expected)
    edges = [e[min(len(e) - 1, (k * len(e)) // bins)] for k in range(1, bins)]

    def hist(xs):
        c = [0] * bins
        for x in xs:
            b = 0
            while b < bins - 1 and x > edges[b]:
                b += 1
            c[b] += 1
        return [max(ci, 1) / (len(xs)) for ci in c]   # Laplace floor to avoid log(0)

    pe = hist(expected); pa = hist(actual)
    return sum((pa[i] - pe[i]) * math.log(pa[i] / pe[i]) for i in range(bins))


def _stdev(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _skew_kurt(xs):
    n = len(xs)
    if n < 4:
        return 0.0, 3.0
    m = sum(xs) / n; sd = _stdev(xs)
    if sd <= 0:
        return 0.0, 3.0
    z = [(x - m) / sd for x in xs]
    sk = sum(t ** 3 for t in z) / n
    ku = sum(t ** 4 for t in z) / n
    return sk, ku


def compute(root=".", window=10, horizon=21):
    alpha_log = os.path.join(root, "data", "alpha_log.jsonl")
    if not os.path.exists(alpha_log):
        alpha_log = os.path.join(root, "alpha_log.jsonl")
    health_log = os.path.join(root, "health_log.jsonl")
    ic_log = os.path.join(root, "data", "factor_ic.jsonl")
    if not os.path.exists(ic_log):
        ic_log = os.path.join(root, "factor_ic.jsonl")

    arows = _read_jsonl(alpha_log)
    resolved = [r for r in arows if r.get("fwd") is not None and r.get("alpha") is not None]
    m = {"asof": dt.date.today().isoformat(), "nResolved": len(resolved), "nLogged": len(arows)}
    alerts = []

    # --- skill: IC / rankIC / hit-rate (overall + recent) ---
    if len(resolved) >= 20:
        preds = [float(r["alpha"]) for r in resolved]
        reals = [float(r["fwd"]) for r in resolved]
        m["IC"] = _round(_pearson(preds, reals))
        m["rankIC"] = _round(_spearman(preds, reals))
        m["hitRate"] = _round(sum(1 for i in range(len(preds))
                                  if (preds[i] > 0) == (reals[i] > 0)) / len(preds))
        # recent window by date
        bydate = {}
        for r in resolved:
            bydate.setdefault(r.get("d", "")[:10], []).append((float(r["alpha"]), float(r["fwd"])))
        recent_dates = sorted(bydate)[-window:]
        rp = [p for d in recent_dates for p in bydate[d]]
        if len(rp) >= 20:
            m["rankIC_recent"] = _round(_spearman([p[0] for p in rp], [p[1] for p in rp]))
        # decile monotonicity of realized payoff
        buckets = _quantile_buckets(list(zip(preds, reals)), 10)
        if buckets:
            m["decileMonotonic"] = _round(_spearman([b[0] for b in buckets], [b[1] for b in buckets]))
            m["decileMeans"] = [_round(b[1], 5) for b in buckets]
        # per-period top-minus-bottom-decile spread -> DSR
        spread = []
        for d in sorted(bydate):
            day = sorted(bydate[d], key=lambda p: p[0])
            if len(day) >= 10:
                k = max(1, len(day) // 10)
                top = sum(p[1] for p in day[-k:]) / k
                bot = sum(p[1] for p in day[:k]) / k
                spread.append(top - bot)
        if len(spread) >= 8 and _dsr:
            sd = _stdev(spread); mean = sum(spread) / len(spread)
            sr = mean / sd if sd > 0 else 0.0
            sk, ku = _skew_kurt(spread)
            d = _dsr(sr, len(spread), skew=sk, kurt=ku, n_trials=1)
            m["spreadSharpe"] = _round(sr); m["spreadDSR"] = d.get("dsr"); m["spreadN"] = len(spread)
        # PSI drift of predicted-alpha distribution: recent window vs prior
        alldates = sorted(bydate)
        if len(alldates) >= 2 * window:
            prior = [p[0] for d in alldates[-2 * window:-window] for p in bydate[d]]
            recent = [p[0] for d in alldates[-window:] for p in bydate[d]]
            m["alphaPSI"] = _round(_psi(prior, recent, 10))
    else:
        m["IC"] = m["rankIC"] = m["hitRate"] = None

    # --- alerts on skill ---
    if m.get("rankIC_recent") is not None and m["rankIC_recent"] < 0:
        alerts.append({"sev": "alert", "metric": "rankIC_recent", "value": m["rankIC_recent"],
                       "msg": "Recent rank-IC is negative — signal may be inverted."})
    elif m.get("rankIC") is not None and m["rankIC"] < 0.0:
        alerts.append({"sev": "warn", "metric": "rankIC", "value": m["rankIC"],
                       "msg": "Overall rank-IC <= 0 — no demonstrated cross-sectional skill."})
    if m.get("decileMonotonic") is not None and m["decileMonotonic"] < 0:
        alerts.append({"sev": "warn", "metric": "decileMonotonic", "value": m["decileMonotonic"],
                       "msg": "Decile payoff is non-monotonic (negative) — miscalibrated ranking."})
    if m.get("alphaPSI") is not None:
        if m["alphaPSI"] > 0.25:
            alerts.append({"sev": "alert", "metric": "alphaPSI", "value": m["alphaPSI"],
                           "msg": "Predicted-alpha distribution shifted materially (PSI>0.25)."})
        elif m["alphaPSI"] > 0.10:
            alerts.append({"sev": "warn", "metric": "alphaPSI", "value": m["alphaPSI"],
                           "msg": "Predicted-alpha distribution drifting (PSI>0.10)."})

    # --- data-health trend ---
    hrows = _read_jsonl(health_log)
    if hrows:
        rec = hrows[-window:]
        def frac_degraded(r):
            dq = r.get("dataQuality") or {}
            tot = sum(v or 0 for v in dq.values()) or 1
            return (dq.get("degraded", 0) or 0 + (dq.get("reject", 0) or 0)) / tot
        degs = []
        for r in rec:
            dq = r.get("dataQuality") or {}
            tot = (dq.get("clean", 0) or 0) + (dq.get("degraded", 0) or 0) + (dq.get("reject", 0) or 0)
            if tot:
                degs.append(((dq.get("degraded", 0) or 0) + (dq.get("reject", 0) or 0)) / tot)
        m["degradedFracRecent"] = _round(sum(degs) / len(degs)) if degs else None
        # fmp degraded streak (consecutive from the end)
        streak = 0
        for r in reversed(hrows):
            if r.get("fmpDegraded"):
                streak += 1
            else:
                break
        m["fmpDegradedStreak"] = streak
        # drift significant fraction
        sigs = []
        for r in rec:
            dc = r.get("driftCensus") or {}
            tot = sum(v or 0 for v in dc.values()) or 0
            if tot:
                sigs.append((dc.get("significant", 0) or 0) / tot)
        m["driftSignificantFracRecent"] = _round(sum(sigs) / len(sigs)) if sigs else None

        if m.get("degradedFracRecent") is not None and m["degradedFracRecent"] > 0.5:
            alerts.append({"sev": "alert", "metric": "degradedFracRecent", "value": m["degradedFracRecent"],
                           "msg": "More than half of recent inputs degraded/rejected."})
        elif m.get("degradedFracRecent") is not None and m["degradedFracRecent"] > 0.25:
            alerts.append({"sev": "warn", "metric": "degradedFracRecent", "value": m["degradedFracRecent"],
                           "msg": "Elevated degraded-input fraction (>25%)."})
        if m.get("fmpDegradedStreak", 0) >= 3:
            alerts.append({"sev": "alert", "metric": "fmpDegradedStreak", "value": m["fmpDegradedStreak"],
                           "msg": "FMP price source degraded for %d+ consecutive builds." % m["fmpDegradedStreak"]})
        if m.get("driftSignificantFracRecent") is not None and m["driftSignificantFracRecent"] > 0.34:
            alerts.append({"sev": "warn", "metric": "driftSignificantFracRecent",
                           "value": m["driftSignificantFracRecent"],
                           "msg": "Many features in significant drift (>1/3)."})

    # --- factor-IC log (informational) ---
    irows = _read_jsonl(ic_log)
    if irows:
        last = irows[-1].get("ic") or {}
        m["factorIClast"] = {k: _round(v) for k, v in last.items()} if last else None

    sev_rank = {"ok": 0, "warn": 1, "alert": 2}
    status = "ok"
    for a in alerts:
        if sev_rank[a["sev"]] > sev_rank[status]:
            status = a["sev"]
    return {"asof": m["asof"], "status": status, "metrics": m, "alerts": alerts,
            "window": window, "horizon": horizon, "schema": "monitoring/1"}


def _round(x, n=4):
    return None if x is None else round(float(x), n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="monitoring/latest.json")
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--strict", action="store_true", help="exit 2 if status==alert")
    a = ap.parse_args()
    rep = compute(a.root, a.window, a.horizon)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rep, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    sys.stderr.write("monitoring: status=%s resolved=%d alerts=%d -> %s\n" % (
        rep["status"], rep["metrics"].get("nResolved", 0), len(rep["alerts"]), a.out))
    for al in rep["alerts"]:
        sys.stderr.write("  [%s] %s (%s=%s)\n" % (al["sev"].upper(), al["msg"], al["metric"], al["value"]))
    return 2 if (a.strict and rep["status"] == "alert") else 0


if __name__ == "__main__":
    raise SystemExit(main())
