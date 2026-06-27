#!/usr/bin/env python3
"""
qa_signoff.py — release QA + provenance sign-off for the MrktPrice publish.

The final integrity layer of the data->output spec. It does three things, all offline,
all pure-stdlib, deterministic, and CI-gateable:

  1. SOURCE FINGERPRINT  — sha256 every build-engine file under tools/market_map/ (and any
     extra source roots) and fold them into ONE deterministic "build fingerprint". This is the
     provenance anchor: the published artifacts are tied to the exact code that produced them.

  2. ARTIFACT MANIFEST   — for each published artifact (marketmap.json, xsection.json, cik.json,
     alpha_calib.json, ...): sha256, byte size, last byte/tail, JSON-validity, and the
     top-level keys. Catches truncated / half-written / empty promotes that JSON-validity alone
     can miss, and records exactly what bytes shipped.

  3. QA CHECKS           — a battery of release gates over the PRIMARY payload:
        - schema/version present and == expected
        - names[] count >= --min-names
        - freshness: asof within --max-age-days of today (UTC)
        - source string present and not the SAMPLE/synthetic fallback
        - dataHealth coverage of core domains (prices/macro/short) >= --min-core-cov
        - quantile non-crossing on every node that carries q-low/q-mid/q-high
        - all node 'net' (or score) fields finite
     HARD checks block the publish (exit 1); SOFT checks warn but still ship.

Outputs a single sign-off JSON (machine) and a short human summary to stdout.
A non-zero exit means "do not publish".

Usage:
    python qa_signoff.py marketmap.json \
        --also xsection.json cik.json alpha_calib.json \
        --src-root tools/market_map \
        --min-names 30 --max-age-days 4 --min-core-cov 0.80 \
        --schema-version 1 \
        --out .build/qa-signoff.json
"""
import argparse, datetime as _dt, hashlib, json, math, os, sys

SAMPLE_MARKERS = ("SAMPLE", "synthetic", "demo", "placeholder", "FALLBACK")


# ---------- low-level ----------
def _sha256_bytes(b):
    h = hashlib.sha256(); h.update(b); return h.hexdigest()


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _file_record(path):
    """sha/size/tail/json-validity for one artifact, from the authoritative bytes."""
    b = _read_bytes(path)
    rec = {
        "path": path,
        "bytes": len(b),
        "sha256": _sha256_bytes(b),
        "tail": b[-1:].decode("utf-8", "replace") if b else "",
        "mtime": _dt.datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat() + "Z",
    }
    try:
        rec["json"] = json.loads(b.decode("utf-8"))
        rec["json_valid"] = True
        rec["top_keys"] = sorted(rec["json"].keys()) if isinstance(rec["json"], dict) else None
    except Exception as e:
        rec["json_valid"] = False
        rec["json_error"] = str(e)
        rec["json"] = None
        rec["top_keys"] = None
    return rec


def source_fingerprint(roots, exts=(".py", ".js", ".mjs")):
    """Deterministic combined hash of every source file under the given roots."""
    files = []
    for root in roots:
        if os.path.isfile(root):
            files.append(root); continue
        for dp, _dn, fn in os.walk(root):
            for name in fn:
                if name.endswith(exts):
                    files.append(os.path.join(dp, name))
    files = sorted(set(os.path.normpath(p) for p in files))
    per = []
    agg = hashlib.sha256()
    for p in files:
        try:
            d = _sha256_bytes(_read_bytes(p))
        except Exception:
            d = "UNREADABLE"
        # fold path + content hash so a rename also changes the fingerprint
        agg.update(os.path.basename(p).encode("utf-8")); agg.update(d.encode("utf-8"))
        per.append({"file": p.replace("\\", "/"), "sha256": d})
    return {"fingerprint": agg.hexdigest(), "n_files": len(files), "files": per}


# ---------- QA checks ----------
def _is_finite(x):
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def qa_checks(payload, *, min_names, max_age_days, min_core_cov,
              schema_version, today=None):
    """Returns (checks list, hard_ok bool). Each check: name, ok, hard, detail."""
    checks = []

    def add(name, ok, hard, detail=""):
        checks.append({"name": name, "ok": bool(ok), "hard": hard, "detail": str(detail)})

    if not isinstance(payload, dict):
        add("payload-is-object", False, True, "top-level JSON is not an object")
        return checks, False

    # schema/version
    ver = payload.get("schemaVersion", payload.get("version", payload.get("schema_version")))
    if schema_version is None:
        add("schema-version-present", ver is not None, False, "version=%r" % ver)
    else:
        add("schema-version-match", str(ver) == str(schema_version), True,
            "got %r expected %r" % (ver, schema_version))

    # names count
    names = payload.get("names")
    if isinstance(names, dict):
        names = list(names.values())
    n = len(names) if isinstance(names, list) else 0
    add("min-names", n >= min_names, True, "names=%d need>=%d" % (n, min_names))

    # freshness
    today = today or _dt.date.today()
    asof = payload.get("asof")
    age = None
    if asof:
        try:
            d = _dt.date.fromisoformat(str(asof)[:10])
            age = (today - d).days
        except Exception:
            age = None
    add("freshness", age is not None and 0 <= age <= max_age_days, True,
        "asof=%r age=%r max=%d" % (asof, age, max_age_days))

    # source not synthetic/sample
    src = str(payload.get("source", ""))
    is_sample = any(m.lower() in src.lower() for m in SAMPLE_MARKERS)
    add("source-not-sample", bool(src) and not is_sample, True, "source=%r" % src[:80])

    # core coverage from dataHealth — supports two real shapes:
    #  (a) flat fractions: dataHealth.prices.coverage = 0..1
    #  (b) count dict:      dataHealth.coverage = {universe, priceOk, shortOk, mcapOk, ...}
    dh = payload.get("dataHealth") or {}
    cov = None
    if isinstance(dh, dict):
        cands = []
        covd = dh.get("coverage")
        if isinstance(covd, dict) and _is_finite(covd.get("universe")) and float(covd["universe"]) > 0:
            uni = float(covd["universe"])
            for k in ("priceOk", "shortOk", "mcapOk"):   # the core domains
                if _is_finite(covd.get(k)):
                    cands.append(float(covd[k]) / uni)
        else:
            for k in ("prices", "macro", "short", "shortInterest", "flow"):
                v = dh.get(k)
                if isinstance(v, dict):
                    v = v.get("coverage", v.get("cov"))
                if _is_finite(v):
                    cands.append(float(v))
        if cands:
            cov = sum(cands) / len(cands)
    if cov is None:
        add("core-coverage", True, False, "no dataHealth coverage to check (soft-pass)")
    else:
        add("core-coverage", cov >= min_core_cov, False,
            "mean core coverage=%.3f need>=%.2f" % (cov, min_core_cov))

    # quantile non-crossing + finite scores
    crossed = 0; nonfinite = 0; checked_q = 0
    if isinstance(names, list):
        for nd in names:
            if not isinstance(nd, dict):
                continue
            # real payload carries analyst price-target band as ptgt={low,tgt,high}
            pt = nd.get("ptgt") if isinstance(nd.get("ptgt"), dict) else None
            if pt:
                ql, qm, qh = pt.get("low"), pt.get("tgt"), pt.get("high")
            else:
                ql = nd.get("qLo", nd.get("qlo", nd.get("p6low", nd.get("low"))))
                qm = nd.get("qMid", nd.get("qmid", nd.get("p6mid", nd.get("mid"))))
                qh = nd.get("qHi", nd.get("qhi", nd.get("p6high", nd.get("high"))))
            if _is_finite(ql) and _is_finite(qm) and _is_finite(qh):
                checked_q += 1
                if not (float(ql) <= float(qm) <= float(qh)):
                    crossed += 1
            sc = nd.get("net", nd.get("score", nd.get("opp", nd.get("oppPct"))))
            if sc is not None and not _is_finite(sc):
                nonfinite += 1
    add("quantile-noncross", crossed == 0, True,
        "crossed=%d of %d quantile-bearing nodes" % (crossed, checked_q))
    add("scores-finite", nonfinite == 0, True, "non-finite score nodes=%d" % nonfinite)

    hard_ok = all(c["ok"] for c in checks if c["hard"])
    return checks, hard_ok


# ---------- driver ----------
def build_signoff(primary, also, src_roots, *, min_names, max_age_days,
                  min_core_cov, schema_version, today=None):
    prec = _file_record(primary)
    arts = [prec] + [_file_record(p) for p in also if os.path.exists(p)]
    fp = source_fingerprint(src_roots)
    checks, hard_ok = qa_checks(
        prec.get("json"), min_names=min_names, max_age_days=max_age_days,
        min_core_cov=min_core_cov, schema_version=schema_version, today=today)
    # strip the heavy embedded json out of the manifest (keep keys only)
    for a in arts:
        a.pop("json", None)
    soft_fail = [c["name"] for c in checks if not c["ok"] and not c["hard"]]
    hard_fail = [c["name"] for c in checks if not c["ok"] and c["hard"]]
    return {
        "generatedUtc": _dt.datetime.utcnow().isoformat() + "Z",
        "verdict": "PASS" if hard_ok else "FAIL",
        "hardOk": hard_ok,
        "hardFailures": hard_fail,
        "softWarnings": soft_fail,
        "sourceFingerprint": fp["fingerprint"],
        "sourceFiles": fp["n_files"],
        "primary": prec["path"],
        "artifacts": arts,
        "checks": checks,
        "source": fp["files"],
    }


def _human(rep):
    lines = ["QA SIGN-OFF: %s  (source fingerprint %s, %d files)"
             % (rep["verdict"], rep["sourceFingerprint"][:12], rep["sourceFiles"])]
    for c in rep["checks"]:
        mark = "PASS" if c["ok"] else ("HARD-FAIL" if c["hard"] else "warn")
        lines.append("  [%-9s] %-22s %s" % (mark, c["name"], c["detail"]))
    lines.append("  artifacts:")
    for a in rep["artifacts"]:
        lines.append("    %-22s %8d bytes  json=%s  sha=%s"
                     % (os.path.basename(a["path"]), a["bytes"],
                        a.get("json_valid"), a["sha256"][:12]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="MrktPrice release QA + provenance sign-off")
    ap.add_argument("primary", help="primary payload (marketmap.json)")
    ap.add_argument("--also", nargs="*", default=[], help="secondary artifacts")
    ap.add_argument("--src-root", nargs="*", default=["tools/market_map"],
                    help="source roots to fingerprint")
    ap.add_argument("--min-names", type=int, default=30)
    ap.add_argument("--max-age-days", type=int, default=4)
    ap.add_argument("--min-core-cov", type=float, default=0.80)
    ap.add_argument("--schema-version", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    rep = build_signoff(
        a.primary, a.also, a.src_root,
        min_names=a.min_names, max_age_days=a.max_age_days,
        min_core_cov=a.min_core_cov, schema_version=a.schema_version)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2)
    print(_human(rep))
    return 0 if rep["hardOk"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
