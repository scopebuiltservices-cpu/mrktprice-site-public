"""Trigger-outcome store (stdlib) — closes the calibration loop for the intraday conviction gate.

Each build, snapshot every name's gate metrics (RVOL, sigma-displacement z, OBV-slope t-stat, EMA
velocity) + the anchor price; once the forward horizon elapses, MATURE each snapshot by attaching the
realized forward return, pooling (metric_value, fwd) pairs across names+dates. threshold_calib then fits
out-of-sample, walk-forward cutoffs from that pooled history (with honest DSR trial counting). Until the
history accrues the board keeps the literature defaults. Append-only JSONL, atomic. Research only.
"""
import os, json, math, datetime
_HERE = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
_sys.path.insert(0, os.path.dirname(_HERE))
try:
    import verify_artifact as _va
except Exception:
    _va = None


def metrics_for(cl, vol):
    """Daily gate metrics from closes+volume: rvol, z (sigma-displacement), obvt (OBV-slope t), vel."""
    c = [x for x in (cl or []) if x and x > 0]; v = vol or []
    n = len(c)
    if n < 25: return None
    sma20 = sum(c[-20:]) / 20.0
    sd20 = math.sqrt(sum((x - sma20) ** 2 for x in c[-20:]) / 19.0) or 1e-9
    z = (c[-1] - sma20) / sd20
    rvol = (v[-1] / (sum(v[-21:-1]) / 20.0)) if (len(v) >= 21 and sum(v[-21:-1]) > 0) else None
    m = min(len(c), len(v))
    obv = [0.0]
    for i in range(1, m):
        obv.append(obv[-1] + (v[i] if c[i] > c[i - 1] else (-v[i] if c[i] < c[i - 1] else 0.0)))
    obvt = None
    if len(obv) >= 8:
        ys = obv[-8:]; mm = 8; mx = (mm - 1) / 2.0; my = sum(ys) / mm
        sxx = sum((k - mx) ** 2 for k in range(mm)); sxy = sum((k - mx) * (ys[k] - my) for k in range(mm))
        sl = sxy / sxx if sxx else 0.0
        sse = sum((my + sl * (k - mx) - ys[k]) ** 2 for k in range(mm))
        se = math.sqrt((sse / (mm - 2)) / sxx) if (sxx and mm > 2) else 0.0
        obvt = sl / se if se > 0 else 0.0
    lp = [math.log(x) for x in c]; k = 2.0 / 22.0; ema = [lp[0]]
    for x in lp[1:]: ema.append(k * x + (1 - k) * ema[-1])
    rets = [lp[i] - lp[i - 1] for i in range(1, len(lp))]
    tail = rets[-60:]; mt = sum(tail) / len(tail)
    sig = math.sqrt(sum((r - mt) ** 2 for r in tail) / max(1, len(tail) - 1)) or 1e-9
    vel = (ema[-1] - ema[-2]) / sig
    return {"rvol": rvol, "z": z, "obvt": obvt, "vel": vel, "px": c[-1]}


def _read(path):
    out = []
    if not os.path.exists(path): return out
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try: out.append(json.loads(ln))
                except Exception: pass
    return out


def _append(path, rec):
    prev = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f: prev = f.read()
        if prev and not prev.endswith("\n"): prev += "\n"
    data = prev + json.dumps(rec, separators=(",", ":")) + "\n"
    if _va: _va.write_atomic(path, data)
    else:
        d = os.path.dirname(os.path.abspath(path)) or "."; os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f: f.write(data)


def snapshot(snap_path, asof, rows):
    """rows=[{t, m:{rvol,z,obvt,vel,px}}]. Idempotent on asof."""
    rows = [r for r in rows if r.get("t") and r.get("m") and r["m"].get("px")]
    if not rows: return False
    for r in _read(snap_path):
        if r.get("asof") == asof: return False
    _append(snap_path, {"asof": asof, "rows": [{"t": str(r["t"]).upper(), "m": r["m"]} for r in rows]})
    return True


def _days(a, b):
    try: return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
    except Exception: return 0


def mature(snap_path, out_path, asof_now, horizon_days, px_now):
    """Attach realized forward return to each snapshot >= horizon old (once), appending pooled
    {origin,metric,value,fwd} rows. Idempotent on origin. Returns count of snapshots matured."""
    done = set(r.get("origin") for r in _read(out_path))
    nm = 0
    for snap in _read(snap_path):
        origin = snap.get("asof")
        if not origin or origin in done or _days(origin, asof_now) < horizon_days: continue
        recs = []
        for r in (snap.get("rows") or []):
            t = r.get("t"); m = r.get("m") or {}; p0 = m.get("px"); p1 = px_now.get(t) if px_now else None
            if not p0 or not p1: continue
            fwd = p1 / p0 - 1.0
            for k in ("rvol", "z", "obvt", "vel"):
                if m.get(k) is not None:
                    recs.append({"origin": origin, "metric": k, "value": m[k], "fwd": fwd})
        for rec in recs: _append(out_path, rec)
        if recs: nm += 1
    return nm


def read_outcomes(out_path, metric):
    """Pooled {values,fwd} for a metric across all matured origins."""
    vals, fwd = [], []
    for r in _read(out_path):
        if r.get("metric") == metric and r.get("value") is not None and r.get("fwd") is not None:
            vals.append(r["value"]); fwd.append(r["fwd"])
    return {"values": vals, "fwd": fwd}
