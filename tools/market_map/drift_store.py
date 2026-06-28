#!/usr/bin/env python3
"""
drift_store.py — per-name return-distribution DRIFT, checkpointed run-over-run (pure stdlib, tested).

Detects when a name's return distribution shifts versus a RETAINED reference window — catching regime
change, a provider swapping its adjustment basis, or a corrupted pull, instead of silently trusting it.

Two signals per name:
  1. run-over-run drift (primary): a frozen reference sample (drift_ref.json) is compared to the current
     window via PSI + KS (data_quality.drift_report). The reference is refreshed only when it ages past
     ref_lag_days, so drift is measured against a stable, weeks-old baseline. Persisted across nightly runs.
  2. in-sample drift (immediate): the current series' older half vs recent window — works from day one,
     before the reference store has matured.

Files
  drift_ref.json     {t: {asof, rets:[...]}}  — frozen reference samples (commit so it persists run-over-run)
  drift_store.jsonl  append per run per name: {asof,t,refAsof,nRef,nCur,psi,ks,level,status}
"""
import json, os, datetime
import data_quality as dq


def _age_days(a, b):
    try:
        da = datetime.date.fromisoformat(str(a)[:10]); db = datetime.date.fromisoformat(str(b)[:10])
        return (db - da).days
    except Exception:
        return 10 ** 6


def load_ref(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_ref(path, ref):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ref, f, separators=(",", ":"))
    os.replace(tmp, path)


def in_sample_drift(rets, frac=0.6, min_n=40):
    """Immediate drift: older `frac` of the series (reference) vs the remaining recent window."""
    r = [x for x in (rets or []) if x is not None]
    if len(r) < min_n:
        return {"psi": None, "ks": None, "level": "insufficient"}
    k = int(len(r) * frac)
    ref, cur = r[:k], r[k:]
    if len(ref) < 20 or len(cur) < 20:
        return {"psi": None, "ks": None, "level": "insufficient"}
    return dq.drift_report(ref, cur)


def update(ref_path, log_path, asof, rets_map, *, ref_lag_days=45, min_n=40, sample=120, bins=10):
    """Compute per-name run-over-run + in-sample drift; refresh aged references; append the log.
    rets_map: {ticker: [log-returns ascending]}. Returns {ticker: drift dict} for payload attachment."""
    ref = load_ref(ref_path)
    out = {}
    log_lines = []
    new_ref = dict(ref)
    for t, rets in (rets_map or {}).items():
        cur = [x for x in (rets or []) if x is not None][-sample:]
        ins = in_sample_drift(rets)
        if len(cur) < min_n:
            out[t] = {"status": "insufficient", "level": "insufficient", "inSample": ins}
            continue
        prev = ref.get(t)
        need_refresh = (not prev) or (len(prev.get("rets", [])) < min_n) or (_age_days(prev.get("asof"), asof) >= ref_lag_days)
        if need_refresh:
            new_ref[t] = {"asof": asof, "rets": cur}
            rec = {"status": "baseline", "level": "baseline", "refAsof": asof,
                   "psi": None, "ks": None, "inSample": ins}
        else:
            dr = dq.drift_report(prev["rets"], cur, bins)
            rec = {"status": "measured", "level": dr["level"], "refAsof": prev.get("asof"),
                   "psi": dr["psi"], "ks": dr["ks"], "inSample": ins}
        out[t] = rec
        log_lines.append(json.dumps({"asof": asof, "t": t, "refAsof": rec["refAsof"],
                                     "nRef": len(new_ref.get(t, {}).get("rets", prev.get("rets", []) if prev else [])),
                                     "nCur": len(cur), "psi": rec["psi"], "ks": rec["ks"],
                                     "level": rec["level"], "status": rec["status"]}))
    if log_lines:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
    save_ref(ref_path, new_ref)
    return out


def census(drift_map):
    """Universe-level drift summary for dataHealth: counts by level + the most-drifted names."""
    c = {"stable": 0, "moderate": 0, "significant": 0, "baseline": 0, "insufficient": 0, "flagged": []}
    ranked = []
    for t, d in (drift_map or {}).items():
        lv = d.get("level", "insufficient")
        c[lv] = c.get(lv, 0) + 1
        if lv in ("moderate", "significant") and d.get("psi") is not None:
            ranked.append((t, d.get("psi"), lv))
    ranked.sort(key=lambda x: -(x[1] or 0))
    c["flagged"] = [{"t": t, "psi": round(p, 3), "level": lv} for t, p, lv in ranked[:25]]
    return c
