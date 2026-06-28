#!/usr/bin/env python3
"""
build_integrity.py — data-integrity / drift / provenance helpers, extracted from build_market_map.py.

Consolidates the honesty layer the build attaches to the payload so it is importable, unit-tested, and the
monolith shrinks to thin calls:
    quality_census(names)            -> universe data-quality + cross-source census  (dataHealth.dataQuality)
    attach_drift(snap, precm, dir)   -> per-name run-over-run drift + driftCensus     (drift_store)
    sanitize_outputs(snap, precm)    -> public n['dq'] + bounded-output guard          (dataHealth.sanitizedFields)
    provenance(snap, precm)          -> rawDataHash + configHash                       (reproducibility)
    health_log_record(snap, sani)    -> one trend row for health_log.jsonl

Delegates the math to data_quality + drift_store (both independently tested). Pure stdlib otherwise.
"""
import os, json, hashlib
import data_quality as dq
import drift_store as ds

_BOUNDS = {"beta": (-15.0, 15.0), "maxDD": (-1.0, 0.0), "dvol": (0.0, 6.0),
           "hv": (0.0, 6.0), "rvol": (0.0, 500.0), "atr": (0.0, 1e7)}


def quality_verdict(closes, vols=None):
    try:
        return dq.series_health(closes, vols)
    except Exception:
        return {"verdict": "unknown", "reasons": []}


def quality_census(names):
    c = {"clean": 0, "degraded": 0, "reject": 0, "unknown": 0, "flagged": [], "xsrcChecked": 0, "xsrcDisagree": 0}
    for n in names or []:
        v = n.get("_dq") or "unknown"
        c[v] = c.get(v, 0) + 1
        xs = n.get("xsrc")
        if xs and xs.get("agree") is not None:
            c["xsrcChecked"] += 1
            if xs.get("agree") is False:
                c["xsrcDisagree"] += 1
        if v in ("degraded", "reject") and len(c["flagged"]) < 30:
            c["flagged"].append({"t": n.get("t"), "v": v, "why": n.get("_dqr")})
    return c


def _rets_map(snap, precm, min_len=41):
    rmap = {}
    for n in (snap.get("names") or []):
        t = (n.get("t") or "").upper(); cl = precm.get(t)
        if not t or not cl or len(cl) < min_len:
            continue
        rmap[t] = [cl[i] / cl[i - 1] - 1.0 for i in range(1, len(cl)) if cl[i - 1]]
    return rmap


def attach_drift(snap, precm, store_dir, ref_lag_days=45):
    rmap = _rets_map(snap, precm)
    if not rmap:
        return {}
    out = ds.update(os.path.join(store_dir, "drift_ref.json"), os.path.join(store_dir, "drift_store.jsonl"),
                    snap.get("asof"), rmap, ref_lag_days=ref_lag_days)
    for n in (snap.get("names") or []):
        d = out.get((n.get("t") or "").upper())
        if d:
            n["drift"] = d
    if isinstance(snap.get("dataHealth"), dict):
        snap["dataHealth"]["driftCensus"] = ds.census(out)
    return out


def sanitize_outputs(snap, precm):
    sani = 0
    for n in (snap.get("names") or []):
        t = (n.get("t") or "").upper(); cl = precm.get(t)
        if cl and len(cl) >= 20:
            try:
                n["dq"] = dq.series_health(cl, None)["verdict"]
            except Exception:
                pass
        for k, (lo, hi) in _BOUNDS.items():
            if n.get(k) is not None:
                gv, _r = dq.guard(n.get(k), lo, hi, k)
                if gv is None:
                    n[k] = None; sani += 1
    if isinstance(snap.get("dataHealth"), dict):
        snap["dataHealth"]["sanitizedFields"] = sani
    return sani


def provenance(snap, precm):
    raw = {t: [round(x, 4) for x in (precm.get(t) or [])] for t in sorted(precm)}
    rawh = hashlib.sha256(json.dumps(raw, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    cfg = {"weights": {"sMR": 0.35, "sMom": 0.30, "sSig": 0.25, "sVol": 0.10}, "thr": 0.3, "H": 10, "schema": snap.get("schemaVersion")}
    cfgh = hashlib.sha256(json.dumps(cfg, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    if isinstance(snap.get("dataHealth"), dict):
        snap["dataHealth"]["rawDataHash"] = rawh
        snap["dataHealth"]["configHash"] = cfgh
    return rawh, cfgh


def health_log_record(snap, sani):
    dh = snap.get("dataHealth") or {}; dqc = dh.get("dataQuality") or {}; drc = dh.get("driftCensus") or {}
    return {"asof": snap.get("asof"), "source": (snap.get("source") or "")[:70],
            "dataQuality": {k: dqc.get(k) for k in ("clean", "degraded", "reject")} if dqc else None,
            "priceSrc": dh.get("priceSrc"), "fmpLastOk": dh.get("fmpLastOk"), "fmpDegraded": dh.get("fmpDegraded"),
            "rateSource": (snap.get("realCurve") or {}).get("source"),
            "driftCensus": {k: drc.get(k) for k in ("stable", "moderate", "significant", "baseline")} if drc else None,
            "sanitizedFields": sani}
