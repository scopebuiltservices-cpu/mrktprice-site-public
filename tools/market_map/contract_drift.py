#!/usr/bin/env python3
"""contract_drift.py — make schema↔payload CONTRACT DRIFT a visible build signal.

The audit's load-bearing complaint was promise-vs-emit drift: the schema/tests/docs advertise fields
the implementation no longer emits (the conformalPad / coveragePadded case). validate_payload.py already
checks required fields + invariants; this complements it by auditing the DECLARED-vs-EMITTED surface:

  ERROR  - a required top-level or required per-name field is missing (hard contract break)
  ERROR  - a field DECLARED in the schema ($defs.name.properties) is emitted by ZERO names
           (the schema promises it but the producer dropped it — exactly the drift the audit flagged)
  WARN   - a field emitted by a MAJORITY of names but NOT declared in the schema
           (undocumented load-bearing field — declare it or the contract is drifting open)
  WARN   - schemaVersion missing/malformed

The schema is intentionally permissive (additionalProperties:true), so undeclared fields are allowed;
this gate surfaces the drift rather than forbidding evolution. Exit 1 on any ERROR (or any WARN with
--strict). Emits GitHub ::error::/::warning:: annotations. Pure stdlib. Verified.

CLI: python3 contract_drift.py marketmap.json [--schema marketmap.schema.json] [--strict] [--min-emit 0.5]
"""
import argparse
import json
import os
import re
import sys


def _load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def audit(payload, schema, min_emit=0.5):
    errors, warns, info = [], [], {}
    req_top = schema.get("required", [])
    for k in req_top:
        if k not in payload:
            errors.append("required top-level field missing: %s" % k)

    names = payload.get("names") or []
    n = len(names)
    name_def = (schema.get("$defs", {}) or {}).get("name", {}) or {}
    declared = set((name_def.get("properties", {}) or {}).keys())
    req_name = set(name_def.get("required", []) or [])

    # per-name required + emission census of declared fields
    emit = {k: 0 for k in declared}
    seen = {}
    miss_req_name = 0
    for rec in names:
        if not isinstance(rec, dict):
            continue
        for rk in req_name:
            if rk not in rec:
                miss_req_name += 1
        for k in rec.keys():
            seen[k] = seen.get(k, 0) + 1
            if k in emit:
                emit[k] += 1
    if miss_req_name:
        errors.append("%d name record(s) missing a required per-name field %s" % (miss_req_name, sorted(req_name)))

    # DECLARED but emitted by ZERO names -> promise-vs-emit drift (the audit's core finding)
    for k in sorted(declared):
        if k in ("t",):           # 't' is the required key; covered above
            continue
        if n > 0 and emit.get(k, 0) == 0:
            errors.append("schema declares name field '%s' but ZERO of %d names emit it (promise-vs-emit drift)" % (k, n))
    info["declaredEmission"] = {k: emit[k] for k in sorted(declared)}

    # emitted by a MAJORITY but NOT declared -> undocumented load-bearing field (doc drift)
    if n > 0:
        for k in sorted(seen):
            if k not in declared and seen[k] >= max(1, int(min_emit * n)):
                warns.append("name field '%s' is emitted by %d/%d names but is NOT declared in the schema (document it)" % (k, seen[k], n))
    info["undeclaredCommon"] = {k: seen[k] for k in sorted(seen) if k not in declared and n and seen[k] >= max(1, int(min_emit * n))}

    sv = payload.get("schemaVersion")
    if not (isinstance(sv, str) and re.match(r"^[0-9]+\.[0-9]+$", sv)):
        warns.append("schemaVersion missing or malformed: %r" % sv)

    return errors, warns, info


def main():
    ap = argparse.ArgumentParser(description="Audit schema↔payload contract drift (declared vs emitted).")
    ap.add_argument("payload")
    ap.add_argument("--schema", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketmap.schema.json"))
    ap.add_argument("--strict", action="store_true", help="treat WARN as failure too")
    ap.add_argument("--min-emit", type=float, default=0.5)
    a = ap.parse_args()
    try:
        payload = _load(a.payload); schema = _load(a.schema)
    except Exception as e:
        sys.stderr.write("contract_drift: cannot load inputs (%s)\n" % e)
        return 1
    errors, warns, info = audit(payload, schema, a.min_emit)

    for e in errors:
        print("::error title=Contract drift::%s" % e)
    for w in warns:
        print("::warning title=Contract drift::%s" % w)
    print("contract_drift: %d ERROR, %d WARN  (declared name fields: %s)" % (
        len(errors), len(warns), ", ".join("%s=%d" % (k, v) for k, v in info.get("declaredEmission", {}).items())))
    for e in errors:
        print("  ERROR  " + e)
    for w in warns:
        print("  WARN   " + w)
    if errors or (a.strict and warns):
        return 1
    print("contract_drift: OK — declared contract matches the emitted payload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
