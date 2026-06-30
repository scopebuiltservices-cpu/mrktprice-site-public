#!/usr/bin/env python3
"""model_registry.py — immutable, append-only provenance registry for every published build.

Audit ask (Tooling/Reproducibility P2): "promote model artifacts as immutable build outputs" and
"attach digests and provenance records so a board row can be traced back to a specific model build,"
keyed by artifact hash, code SHA, data SHA, and calibration run id.

This writes ONE append-only line per build to model_registry.jsonl:
    {ts, codeSha, calibrationRunId, dataSha, artifacts:{name:{sha256,bytes}}, schema}
- codeSha          = `git rev-parse HEAD` (the exact engine commit that produced the artifacts)
- artifacts.sha256 = content digest of each published JSON (marketmap/xsection/projlearn/...)
- dataSha          = a stable digest over the per-artifact digests (the build's overall data fingerprint)
- calibrationRunId = optional id of the calibration run (env CALIB_RUN_ID or a derived stamp)
The registry is APPEND-ONLY and idempotent: a build whose dataSha matches the last entry is not
re-appended (re-runs that change nothing don't bloat the ledger). Pure stdlib; no network. Verified.

CLI: python3 model_registry.py --root . --artifacts marketmap.json xsection.json projlearn.json cik.json \
        --out model_registry.jsonl [--calib-run-id <id>]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys


def _sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest(), os.path.getsize(path)
    except Exception:
        return None, None


def _code_sha(root):
    for args in (["git", "-C", root, "rev-parse", "HEAD"], ["git", "rev-parse", "HEAD"]):
        try:
            p = subprocess.run(args, capture_output=True, text=True)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.strip()
        except Exception:
            pass
    return os.environ.get("GITHUB_SHA", "").strip() or None


def build_entry(root, artifacts, calib_run_id=None):
    arts = {}
    for a in artifacts:
        path = a if os.path.isabs(a) else os.path.join(root, a)
        sha, n = _sha256_file(path)
        if sha is not None:
            arts[os.path.basename(a)] = {"sha256": sha, "bytes": n}
    # dataSha = digest over the sorted per-artifact digests (stable build fingerprint)
    joined = ";".join("%s=%s" % (k, arts[k]["sha256"]) for k in sorted(arts))
    data_sha = hashlib.sha256(joined.encode("utf-8")).hexdigest() if joined else None
    return {
        "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "codeSha": _code_sha(root),
        "calibrationRunId": (calib_run_id or os.environ.get("CALIB_RUN_ID") or None),
        "dataSha": data_sha,
        "artifacts": arts,
        "schema": "modelRegistry/1",
    }


def last_entry(out_path):
    if not os.path.exists(out_path):
        return None
    last = None
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
        return json.loads(last) if last else None
    except Exception:
        return None


def register(root, artifacts, out_path, calib_run_id=None):
    """Append a build entry unless its dataSha matches the last one (idempotent). Returns (entry, appended)."""
    entry = build_entry(root, artifacts, calib_run_id)
    if not entry["artifacts"]:
        return entry, False
    prev = last_entry(out_path)
    if prev and prev.get("dataSha") and prev["dataSha"] == entry["dataSha"]:
        return entry, False                                  # nothing changed -> don't bloat the ledger
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    return entry, True


def main():
    ap = argparse.ArgumentParser(description="Append an immutable provenance entry for the current build.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--artifacts", nargs="*", default=["marketmap.json", "xsection.json", "projlearn.json",
                                                       "cik.json", "alpha_calib.json"])
    ap.add_argument("--out", default="model_registry.jsonl")
    ap.add_argument("--calib-run-id", default=None)
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    out_path = a.out if os.path.isabs(a.out) else os.path.join(root, a.out)
    entry, appended = register(root, a.artifacts, out_path, a.calib_run_id)
    if not entry["artifacts"]:
        sys.stderr.write("model_registry: no artifacts found to register — skipped\n")
        return 0
    sys.stderr.write("model_registry: %s build %s (code %s, %d artifacts) -> %s\n" % (
        "appended" if appended else "unchanged (idempotent)", (entry["dataSha"] or "?")[:12],
        (entry["codeSha"] or "?")[:12], len(entry["artifacts"]), out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
