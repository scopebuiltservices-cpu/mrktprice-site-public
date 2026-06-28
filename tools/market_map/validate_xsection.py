#!/usr/bin/env python3
"""
validate_xsection.py — contract gate for xsection.json against xsection.schema.json (stdlib).

Mirrors validate_payload.py's discipline for the cross-section payload: required keys, ticker list,
square correlation matrix aligned to tickers with entries in [-1,1], finite betas/RS in plausible bands.
A violation exits non-zero so CI refuses to publish a malformed cross-section. Research only.

Usage: python validate_xsection.py xsection.json
"""
import json, math, sys


def validate(obj):
    errs = []
    if not isinstance(obj, dict):
        return ["top-level is not an object"]
    if not obj.get("asof"):
        errs.append("missing asof")
    tks = obj.get("tickers")
    if not isinstance(tks, list) or not tks:
        errs.append("tickers must be a non-empty array")
        return errs
    if not all(isinstance(t, str) for t in tks):
        errs.append("tickers must all be strings")
    n = len(tks)
    corr = obj.get("corr")
    if corr is not None:
        if not isinstance(corr, list) or len(corr) != n:
            errs.append("corr must be %d x %d" % (n, n))
        else:
            for i, row in enumerate(corr):
                if not isinstance(row, list) or len(row) != n:
                    errs.append("corr row %d wrong length" % i); break
                for v in row:
                    if v is None:
                        continue
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        errs.append("corr has non-numeric entry"); break
                    if not math.isfinite(fv) or fv < -1.0001 or fv > 1.0001:
                        errs.append("corr entry out of [-1,1]: %r" % v); break
    for key, lo, hi in (("beta", -15.0, 15.0), ("rs", 0.0, 100.0)):
        d = obj.get(key)
        if isinstance(d, dict):
            for k, v in d.items():
                if v is None:
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    errs.append("%s[%s] non-numeric" % (key, k)); continue
                if not math.isfinite(fv) or fv < lo - 1e-6 or fv > hi + 1e-6:
                    errs.append("%s[%s]=%r out of [%g,%g]" % (key, k, v, lo, hi))
    return errs


def main(argv=None):
    argv = argv or sys.argv[1:]
    path = argv[0] if argv else "xsection.json"
    try:
        obj = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("xsection load failed: %s" % e); return 1
    errs = validate(obj)
    if errs:
        print("xsection.json CONTRACT VIOLATIONS:")
        for e in errs[:20]:
            print("  - " + e)
        return 1
    print("xsection.json OK: %d tickers, corr=%s" % (len(obj.get("tickers", [])), "yes" if obj.get("corr") else "no"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
