#!/usr/bin/env python3
"""Validate a freshly-built Market Map snapshot, then publish it only if sane.

Refuses to overwrite the destination unless the new snapshot passes structural checks,
so a partial / failed live fetch can never wipe the committed good data.

Usage:
    validate_publish.py <src.json> <dest.json> [--min-names N] [--check-only]

Exit codes:  0 = published (or check-only passed)   1 = rejected / error.
CI-friendly: prints ::error:: / ::notice:: annotations that surface in the run summary.
"""
from __future__ import annotations
import argparse, json, os, sys, tempfile


def _err(msg):
    print("::error title=validate_publish::%s" % msg)


def validate(d, min_names):
    """Return (ok, reason). Pure — no I/O — so it is unit-testable."""
    names = d.get("names")
    if not isinstance(names, list):
        return False, "snapshot has no 'names' list"
    if len(names) < min_names:
        return False, "too few names (%d < %d) — refusing to publish" % (len(names), min_names)
    missing = [n.get("t", "?") for n in names if not ("z" in n and "ret" in n)]
    if missing:
        return False, "%d name(s) missing metric fields (z/ret), e.g. %s" % (len(missing), missing[:5])
    return True, "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate then publish a Market Map snapshot.")
    ap.add_argument("src")
    ap.add_argument("dest")
    ap.add_argument("--min-names", type=int, default=30, help="reject if fewer names (default 30)")
    ap.add_argument("--check-only", action="store_true", help="validate only; do not write dest")
    a = ap.parse_args(argv)

    try:
        with open(a.src) as f:
            d = json.load(f)
    except Exception as e:
        _err("cannot read %s: %s" % (a.src, e)); return 1

    ok, reason = validate(d, a.min_names)
    if not ok:
        _err(reason); return 1

    if a.check_only:
        print("::notice::validate_publish: OK (check-only) — %d names, asof %s"
              % (len(d["names"]), d.get("asof")))
        return 0

    # atomic write so a crash mid-write can't leave a truncated dest
    try:
        dirn = os.path.dirname(os.path.abspath(a.dest)) or "."
        fd, tmp = tempfile.mkstemp(dir=dirn, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(d, f, separators=(",", ":"), allow_nan=False)
        os.replace(tmp, a.dest)
    except Exception as e:
        _err("write failed: %s" % e); return 1

    print("::notice::Market Map refreshed: %d names, asof %s" % (len(d["names"]), d.get("asof")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
