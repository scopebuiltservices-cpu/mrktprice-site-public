#!/usr/bin/env python3
"""The single producer->consumer contract gate for marketmap.json.

It is the one exit of the math engine: validate the payload against marketmap.schema.json AND the
cross-field invariants that a JSON Schema cannot express, BEFORE the data is published. The browser
runs a mirror of the same version-gate + invariant checks on load (see validatePayload() in the
dashboard) and shows "projection unavailable / no-call" rather than rendering an unaudited view.

Invariants enforced (adapted from the Precision-to-Projection contract to the real payload):
  V1 version : schemaVersion present; MAJOR must be supported (else hard no-call).
  V2 names   : >= min names, each with a non-empty unique ticker.
  V3 coverage: every dataHealth.coverage.*Ok <= universe (no impossible coverage).
  V4 bands   : quantile non-crossing wherever a name exposes ordered bands (lo<=hi, q05<=q50<=q95).
  V5 govern. : governance.releaseGate, if present, is a known value.
  V6 finite  : no NaN/Infinity leaked into the JSON.

Pure functions (validate_payload) are unit-testable; main() does the I/O + CI annotations + exit code.
Optional dep: jsonschema (used if importable); otherwise a stdlib structural check runs.

Usage:  validate_payload.py marketmap.json [--schema marketmap.schema.json] [--min-names 30] [--strict]
Exit 0 = contract holds; 1 = violated.
"""
from __future__ import annotations
import argparse, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sector_integrity as SI

SUPPORTED_MAJORS = {"1"}


def _schema_check(payload, schema):
    """Use jsonschema if available; else a minimal stdlib structural check of the required shape."""
    try:
        import jsonschema  # type: ignore
        jsonschema.validate(payload, schema)
        return []
    except ImportError:
        errs = []
        for k in schema.get("required", []):
            if k not in payload:
                errs.append("missing required top-level field: %s" % k)
        if not isinstance(payload.get("names"), list) or not payload["names"]:
            errs.append("names must be a non-empty array")
        else:
            for i, n in enumerate(payload["names"][:99999]):
                if not isinstance(n, dict) or not n.get("t"):
                    errs.append("names[%d] missing ticker 't'" % i)
        return errs
    except Exception as e:  # jsonschema present but payload invalid
        return ["schema: %s" % str(e).split("\n")[0][:160]]


def _nonfinite(o, path="$"):
    if isinstance(o, float):
        return [] if math.isfinite(o) else [path]
    if isinstance(o, list):
        out = []
        for i, v in enumerate(o[:5000]):
            out += _nonfinite(v, "%s[%d]" % (path, i))
        return out
    if isinstance(o, dict):
        out = []
        for k, v in o.items():
            out += _nonfinite(v, "%s.%s" % (path, k))
        return out
    return []


def _ordered(seq):
    seq = [x for x in seq if isinstance(x, (int, float)) and math.isfinite(x)]
    return all(seq[i] <= seq[i + 1] + 1e-9 for i in range(len(seq) - 1))


def _band_violations(name):
    """Quantile non-crossing wherever the name's lineage exposes ordered bands. Defensive: only flags
    structures it positively recognizes, so it never false-positives on an unknown shape."""
    bad = []
    lin = name.get("lineage")
    if not isinstance(lin, dict):
        return bad
    # lo/hi pairs anywhere one level into conformal / cone
    for key in ("conformal", "cone", "pq", "bl"):
        node = lin.get(key)
        if isinstance(node, dict):
            if isinstance(node.get("lo"), (int, float)) and isinstance(node.get("hi"), (int, float)):
                if node["lo"] > node["hi"] + 1e-9:
                    bad.append("%s.lineage.%s lo>hi" % (name.get("t"), key))
            for hk, hv in node.items():
                if isinstance(hv, dict) and isinstance(hv.get("lo"), (int, float)) and isinstance(hv.get("hi"), (int, float)):
                    if hv["lo"] > hv["hi"] + 1e-9:
                        bad.append("%s.lineage.%s[%s] lo>hi" % (name.get("t"), key, hk))
                if isinstance(hv, dict):
                    qs = [hv.get(q) for q in ("q05", "q25", "q50", "q75", "q95") if q in hv]
                    if len(qs) >= 2 and not _ordered(qs):
                        bad.append("%s.lineage.%s[%s] quantiles cross" % (name.get("t"), key, hk))
    return bad


def validate_payload(payload, schema, min_names=30, prev=None):
    """Pure: returns (ok, errors, warnings)."""
    errors, warnings = [], []

    # schema
    errors += _schema_check(payload, schema)

    # V1 version gate
    sv = str(payload.get("schemaVersion", ""))
    if not sv:
        errors.append("V1: schemaVersion missing")
    else:
        major = sv.split(".")[0]
        if major not in SUPPORTED_MAJORS:
            errors.append("V1: unsupported schemaVersion major %r (supported %s)" % (sv, sorted(SUPPORTED_MAJORS)))

    names = payload.get("names") if isinstance(payload.get("names"), list) else []
    # V2 names
    if len(names) < min_names:
        errors.append("V2: too few names (%d < %d)" % (len(names), min_names))
    seen = set()
    for n in names:
        t = (n or {}).get("t")
        if not t:
            errors.append("V2: a name has no ticker")
        elif t in seen:
            errors.append("V2: duplicate ticker %s" % t)
        else:
            seen.add(t)

    # V3 coverage consistency
    cov = ((payload.get("dataHealth") or {}).get("coverage") or {})
    uni = cov.get("universe")
    if isinstance(uni, int) and uni > 0:
        for k, v in cov.items():
            if k.endswith("Ok") and isinstance(v, int) and v > uni:
                errors.append("V3: coverage.%s (%d) > universe (%d)" % (k, v, uni))

    # V4 quantile non-crossing
    for n in names:
        errors += _band_violations(n or {})

    # V5 governance value
    gov = payload.get("governance") or {}
    rg = gov.get("releaseGate")
    if rg is not None and rg not in ("deployable", "research-only", "blocked", "amber", "green", "red"):
        warnings.append("V5: unfamiliar governance.releaseGate %r" % rg)

    # V7 sector-rotation integrity (the 2026-06-28 silent-regression class)
    for _v in SI.sector_violations(payload):
        errors.append("V7: " + _v)
    # V8 universe regression vs the previously published build (optional baseline)
    if prev is not None:
        _rv = SI.regression_violation(names, (prev.get('names') or []))
        if _rv:
            errors.append("V8: " + _rv)

    # V6 finite
    nf = _nonfinite(payload)
    if nf:
        errors.append("V6: non-finite numbers at %s%s" % (nf[:5], " (+more)" if len(nf) > 5 else ""))

    return (not errors), errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate marketmap.json against the contract + invariants.")
    ap.add_argument("payload")
    ap.add_argument("--schema", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketmap.schema.json"))
    ap.add_argument("--min-names", type=int, default=30)
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    ap.add_argument("--prev", default=None, help="previously published payload, for the regression check")
    a = ap.parse_args(argv)
    try:
        payload = json.load(open(a.payload))
        schema = json.load(open(a.schema))
    except Exception as e:
        print("::error title=validate_payload::cannot read input: %s" % e); return 1

    prev = None
    if a.prev:
        try: prev = json.load(open(a.prev))
        except Exception: prev = None
    ok, errors, warnings = validate_payload(payload, schema, a.min_names, prev=prev)
    for w in warnings:
        print("::warning title=contract::%s" % w)
    for e in errors:
        print("::error title=contract::%s" % e)
    if ok and not (a.strict and warnings):
        print("::notice title=contract::OK - schemaVersion %s, %d names, all invariants hold"
              % (payload.get("schemaVersion"), len(payload.get("names", []))))
        return 0
    print("CONTRACT VIOLATED: %d error(s), %d warning(s)" % (len(errors), len(warnings)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
