#!/usr/bin/env python3
"""
schema_validate.py — validate emitted JSON artifacts against the DECLARATIVE Draft 2020-12 schemas in
schemas/, using the standard `jsonschema` library. The schema files are the single, language-agnostic
source of truth for each contract (Python emits, the browser consumes the SAME schema), which a
hand-rolled Python validator can never be. We deliberately do NOT hand-roll a JSON Schema validator
(that is the anti-pattern this is meant to remove) — we use the canonical `jsonschema` engine.

Division of labour:
  * schema_validate.py (this) -> declarative shape/type/enum/range/pattern via JSON Schema.
  * validate_artifacts.py     -> cross-field INVARIANTS JSON Schema can't express (count == len(members),
                                 duplicate-ticker detection). Both run in CI for belt-and-suspenders.

If `jsonschema` is not installed (stdlib-only local runs), this prints a skip notice and exits 0;
CI installs jsonschema so the strict contract gate is enforced there.
CLI:  python3 schema_validate.py cik.json alpha_calib.json events.json universe.json
"""
import json, os, sys

SCHEMA_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "schemas"))
MAP = {
    "cik.json": "cik.schema.json",
    "alpha_calib.json": "alpha_calib.schema.json",
    "events.json": "events.schema.json",
    "universe.json": "universe.schema.json",
}


def validate(path):
    """Return (True ok | False fail | None skip, info)."""
    base = os.path.basename(path)
    sf = MAP.get(base)
    if not sf:
        return None, "no schema mapped"
    sp = os.path.join(SCHEMA_DIR, sf)
    if not os.path.exists(sp):
        return None, "schema file missing: %s" % sf
    try:
        import jsonschema
        from jsonschema import validators
    except Exception:
        return None, "jsonschema not installed (CI enforces)"
    try:
        schema = json.load(open(sp))
        inst = json.load(open(path))
    except Exception as e:
        return False, ["invalid JSON: %s" % e]
    # Version-robust: prefer the Draft 2020-12 validator; on older jsonschema, auto-select from $schema.
    cls = getattr(jsonschema, "Draft202012Validator", None) or validators.validator_for(schema)
    validator = cls(schema)
    errs = sorted(validator.iter_errors(inst), key=lambda e: list(e.path))
    if errs:
        return False, ["%s: %s" % ("/".join(map(str, e.path)) or "<root>", e.message) for e in errs[:25]]
    return True, []


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: schema_validate.py <file.json> [...]", file=sys.stderr)
        return 2
    rc = 0
    for p in argv:
        base = os.path.basename(p)
        if not os.path.exists(p):
            print("  skip  %s (absent)" % base); continue
        ok, info = validate(p)
        if ok is None:
            print("  skip  %s (%s)" % (base, info)); continue
        if ok:
            print("  ok    %s vs schemas/%s" % (base, MAP[base]))
        else:
            rc = 1; print("  FAIL  %s" % base)
            for e in info:
                print("        " + e)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
