#!/usr/bin/env python3
"""Hardened artifact write + verification (Python stdlib only).

Implements the central principle of the hardened-workflow report: a stale or truncated filesystem
VIEW must never be accepted as a good write. The only acceptance boundary is re-reading the final
bytes from the AUTHORITATIVE target path and matching a manifest (sha256 + byte count + tail sentinel).

Pieces
------
  write_atomic(path, data)   same-directory temp -> flush -> fsync -> os.replace -> RE-READ + sha256 verify
  file_record(path)          {path, sha256, bytes, lines, tail} read from the authoritative path
  build_manifest(paths)      manifest dict for a set of files
  verify_manifest(manifest)  (ok, problems[]) by re-reading each path and comparing sha256/bytes/tail

CLI
---
  manifest <paths...> --out m.json   write a manifest (atomically)
  verify   <m.json>                  re-read every listed file and confirm it still matches
  guard    <path> [--min-bytes N] [--ends-with S]   fail loudly on a missing/truncated/empty promote

Exit code is non-zero on any mismatch so this can gate a build. No third-party dependencies.
"""
import argparse, hashlib, json, os, re, sys, tempfile


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def file_record(path):
    """Byte-level fingerprint of the file AT path (authoritative re-read)."""
    b = _read_bytes(path)
    rec = {"path": path, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
    try:
        t = b.decode("utf-8")
        rec["lines"] = t.count("\n") + (0 if (t == "" or t.endswith("\n")) else 1)
        rec["tail"] = t[-48:]
    except UnicodeDecodeError:
        rec["lines"] = None
        rec["tail"] = None
        rec["binary"] = True
    return rec


def write_atomic(path, data):
    """Write `data` to `path` durably and atomically, then RE-READ and verify the bytes match.

    Same-directory temp (os.replace is only atomic within one filesystem) -> flush -> os.fsync ->
    os.replace -> best-effort parent-dir fsync -> re-read + sha256 compare. Raises RuntimeError if the
    re-read does not match what was written (this is the mount/cache-illusion guard). Returns sha256."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".__atomic_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:                                            # parent-dir durability (Unix only)
            dfd = os.open(d, os.O_DIRECTORY)
            os.fsync(dfd)
            os.close(dfd)
        except (AttributeError, OSError):
            pass
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    want = hashlib.sha256(data).hexdigest()
    got = hashlib.sha256(_read_bytes(path)).hexdigest()
    if want != got:
        raise RuntimeError("atomic write verify FAILED for %s: wrote %s.. but re-read %s.." % (path, want[:12], got[:12]))
    return want


def build_manifest(paths):
    return {"version": 1, "files": [file_record(p) for p in paths]}


def verify_manifest(man):
    """Re-read every file in the manifest from its authoritative path and compare. Returns (ok, problems)."""
    probs = []
    for rec in man.get("files", []):
        p = rec["path"]
        if not os.path.exists(p):
            probs.append("%s: MISSING" % p)
            continue
        cur = file_record(p)
        if cur["sha256"] != rec.get("sha256"):
            probs.append("%s: sha256 mismatch (manifest %s.. disk %s..)" % (p, str(rec.get("sha256"))[:12], cur["sha256"][:12]))
        if cur["bytes"] != rec.get("bytes"):
            probs.append("%s: byte-count mismatch (manifest %s disk %d) — TRUNCATION/STALE VIEW" % (p, rec.get("bytes"), cur["bytes"]))
        if rec.get("tail") is not None and cur.get("tail") != rec.get("tail"):
            probs.append("%s: tail/sentinel mismatch — TRUNCATION" % p)
    return (len(probs) == 0, probs)


def guard(path, min_bytes=0, ends_with=None):
    """Loud guard for a freshly-promoted artifact: exists, >= min_bytes, ends with the expected
    sentinel (after trailing whitespace). Catches the empty/half-written/truncated promote."""
    if not os.path.exists(path):
        return ["%s: MISSING" % path]
    b = _read_bytes(path)
    out = []
    if len(b) < min_bytes:
        out.append("%s: only %d bytes (< required %d) — empty/truncated promote" % (path, len(b), min_bytes))
    if ends_with:
        try:
            tail = b.decode("utf-8").rstrip()
        except UnicodeDecodeError:
            tail = ""
        if not tail.endswith(ends_with):
            out.append("%s: does not end with %r (last 24: %r) — truncated" % (path, ends_with, tail[-24:]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hardened artifact manifest + verification.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest"); m.add_argument("paths", nargs="+"); m.add_argument("--out", required=True)
    v = sub.add_parser("verify"); v.add_argument("manifest")
    g = sub.add_parser("guard"); g.add_argument("path"); g.add_argument("--min-bytes", type=int, default=0); g.add_argument("--ends-with", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "manifest":
        man = build_manifest(a.paths)
        write_atomic(a.out, json.dumps(man, indent=2))
        print("manifest: %d file(s) -> %s" % (len(man["files"]), a.out))
        return 0
    if a.cmd == "verify":
        man = json.load(open(a.manifest))
        ok, probs = verify_manifest(man)
        for p in probs:
            print("::error title=artifact-verify::" + p)
        print("VERIFY: %s (%d file(s))" % ("OK" if ok else "FAILED", len(man.get("files", []))))
        return 0 if ok else 1
    if a.cmd == "guard":
        probs = guard(a.path, a.min_bytes, a.ends_with)
        for p in probs:
            print("::error title=artifact-guard::" + p)
        print("GUARD %s: %s" % (a.path, "OK" if not probs else "FAILED"))
        return 0 if not probs else 1


if __name__ == "__main__":
    raise SystemExit(main())
