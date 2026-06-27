"""Factor IC accumulation store (stdlib).

Snapshots per-name factor exposures every build, then MATURES each snapshot into a cross-sectional
Spearman-IC record once the forward horizon has elapsed — so factor_eval can weight factors by REALIZED
forward predictive power instead of a contemporaneous diagnostic. Two append-only JSONL files (atomic):

  snapshots:  {"asof":"2026-06-26","rows":[{"t":"AAPL","px":201.3,"F":{"mom":1.2,"vel":-0.3,...}}, ...]}
  ic history: {"origin":"2026-05-29","asof":"2026-06-26","h":20,"ic":{"mom":0.07,"vel":0.11,...}}

Maturation rule: a snapshot is matured exactly once, on the first build that is >= horizon calendar days
after its origin; forward return per name = px_now/px_origin - 1; IC = Spearman(exposure, fwd) across the
names present in both. Idempotent on (origin,h). Research only.
"""
import json, os, datetime
_HERE = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
_sys.path.insert(0, os.path.dirname(_HERE))            # tools/ for verify_artifact
try:
    import verify_artifact as _va
except Exception:
    _va = None
import factor_eval as _fe


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
        with open(path, encoding="utf-8") as f:
            prev = f.read()
        if prev and not prev.endswith("\n"): prev += "\n"
    data = prev + json.dumps(rec, separators=(",", ":")) + "\n"
    if _va: _va.write_atomic(path, data)
    else:
        d = os.path.dirname(os.path.abspath(path)) or "."; os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f: f.write(data)


def snapshot(snap_path, asof, rows):
    """Append one snapshot of {t, px, F:{factor:val}} rows. Idempotent on asof."""
    if not rows: return False
    for r in _read(snap_path):
        if r.get("asof") == asof: return False
    clean = [{"t": str(x["t"]).upper(), "px": x["px"], "F": x["F"]} for x in rows
             if x.get("t") and x.get("px") and isinstance(x.get("F"), dict)]
    if not clean: return False
    _append(snap_path, {"asof": asof, "rows": clean})
    return True


def _days(a, b):
    try:
        return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
    except Exception:
        return 0


def mature(snap_path, ic_path, asof_now, horizon_days, px_now):
    """Mature every snapshot >= horizon_days old and not yet matured at this horizon. px_now: {t:price}.
    Appends one IC record per matured origin. Returns the number matured."""
    done = set((r.get("origin"), r.get("h")) for r in _read(ic_path))
    nmat = 0
    for snap in _read(snap_path):
        origin = snap.get("asof")
        if not origin or (origin, horizon_days) in done: continue
        if _days(origin, asof_now) < horizon_days: continue
        rows = snap.get("rows") or []
        facs = {}
        for r in rows:
            for k in (r.get("F") or {}): facs.setdefault(k, True)
        exp = {f: [] for f in facs}; fwd = []
        for r in rows:
            t = r.get("t"); p0 = r.get("px"); p1 = px_now.get(t) if px_now else None
            if not t or not p0 or not p1: continue
            fr = p1 / p0 - 1.0
            ok = True
            for f in facs:
                v = (r.get("F") or {}).get(f)
                if v is None: ok = False; break
            if not ok: continue
            for f in facs: exp[f].append((r.get("F") or {})[f])
            fwd.append(fr)
        if len(fwd) < 5: continue
        ic = {f: round(_fe.spearman_ic(exp[f], fwd), 5) for f in facs}
        _append(ic_path, {"origin": origin, "asof": asof_now, "h": horizon_days, "n": len(fwd), "ic": ic})
        nmat += 1
    return nmat


def read_history(ic_path, horizon_days=None):
    """Return {factor: [IC ordered by origin]} from matured records (optionally one horizon)."""
    recs = _read(ic_path)
    if horizon_days is not None:
        recs = [r for r in recs if r.get("h") == horizon_days]
    recs.sort(key=lambda r: r.get("origin") or "")
    hist = {}
    for r in recs:
        for f, v in (r.get("ic") or {}).items():
            hist.setdefault(f, []).append(v)
    return hist
