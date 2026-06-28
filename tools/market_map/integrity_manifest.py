#!/usr/bin/env python3
"""
integrity_manifest.py — repository content-integrity tripwire for the CRITICAL source surface.

Generalizes the single-module metrics guard into a manifest-driven verifier (think Tripwire/AIDE, but
for source files). It catches the ENTIRE corruption class — NUL bytes, gross truncation, unparseable
source, and SILENT API-surface loss (a canonical estimator vanishing) — WITHOUT brittle whole-file hash
gating, so an intended edit doesn't trip it but corruption always does.

Per-file record: sha256, bytes, lines, nul, kind, parses, api[].
  api = top-level def/class names (+ __all__) for .py; function defs + export-object names for .js/.mjs;
        [] for .json (validity handled by `parses`).

CLI:
  --write   (re)generate tools/integrity.manifest.json  — a CONSCIOUS act; run after intended edits.
            Refuses to write if any tracked file is currently corrupt (won't bake corruption into truth).
  --check   (default) verify the working tree vs the committed manifest.

Severities:
  HARD (exit 1, == corruption): file MISSING; NUL bytes; fails to parse; line count fell below
        committed * FLOOR (gross truncation); a manifest-listed API symbol is now MISSING.
  SOFT (exit 0, notice): content sha changed but the file parses + API intact (benign edit -> --write).
"""
import argparse, ast, hashlib, json, os, re, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MANIFEST = os.path.join(ROOT, "tools", "integrity.manifest.json")
FLOOR = 0.5   # a critical file may not silently lose more than half its lines

# Curated critical surface: canonical libs, extracted modules, engines, the verified references,
# the gate scripts, and the JSON schema contracts. Corruption of any of these is high-impact.
CRITICAL = [
    "tools/market_map/metrics.py", "tools/market_map/price_source.py", "tools/market_map/build_integrity.py",
    "tools/market_map/intraday_engine.py", "tools/market_map/fib_ref.py", "tools/market_map/engine_ref.py",
    "tools/market_map/pooled_rigor.py", "tools/market_map/composite_gate.py", "tools/market_map/data_quality.py",
    "tools/market_map/drift_store.py", "tools/market_map/rate_real.py", "tools/market_map/factor_eval.py",
    "tools/market_map/schema_validate.py", "tools/market_map/validate_artifacts.py",
    "tools/market_map/coverage_regression.py", "tools/market_map/build_market_map.py",
    "engine.js", "intraday_engine.js",
    "tools/check-duplication.mjs", "tools/check-file-budget.mjs",
]


def critical_files():
    paths = [p for p in CRITICAL if os.path.exists(os.path.join(ROOT, p))]
    sd = os.path.join(ROOT, "schemas")
    if os.path.isdir(sd):
        paths += ["schemas/" + f for f in sorted(os.listdir(sd)) if f.endswith(".json")]
    return paths


def _py_api(text):
    # Track actual top-level DEFINITIONS (not names merely listed in __all__), so a truncation that drops
    # `def ewma_vol` while the top-of-file __all__ survives is still caught as a vanished definition.
    return sorted(set(re.findall(r"^(?:def|class)\s+([A-Za-z_]\w*)", text, re.M)))


def _js_api(text):
    names = set(re.findall(r"^\s*function\s+([A-Za-z_]\w*)", text, re.M))
    for blk in re.finditer(r"(?:const\s+API|module\.exports)\s*=\s*\{([^}]*)\}", text):
        names |= set(re.findall(r"[A-Za-z_]\w*", blk.group(1)))
    return sorted(names)


def build_record(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return None
    raw = open(p, "rb").read()
    nul = b"\x00" in raw
    try:
        text = raw.decode("utf-8")
        decoded = True
    except Exception:
        text, decoded = "", False
    kind = os.path.splitext(rel)[1]
    parses = decoded and not nul
    if parses and kind == ".py":
        try:
            ast.parse(text)
        except Exception:
            parses = False
    elif parses and kind == ".json":
        try:
            json.loads(text)
        except Exception:
            parses = False
    api = _py_api(text) if kind == ".py" else (_js_api(text) if kind in (".js", ".mjs") else [])
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return {"path": rel, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "lines": lines, "nul": nul, "kind": kind, "parses": parses, "api": api}


def build_manifest():
    return {"version": 1, "files": [r for r in (build_record(p) for p in critical_files()) if r]}


def check(manifest):
    hard, soft = [], []
    for rec in manifest["files"]:
        cur = build_record(rec["path"])
        if cur is None:
            hard.append((rec["path"], "MISSING from tree")); continue
        if cur["nul"]:
            hard.append((rec["path"], "NUL bytes present (corruption)"))
        if not cur["parses"]:
            hard.append((rec["path"], "does not parse (truncation/corruption)"))
        if cur["lines"] < rec["lines"] * FLOOR:
            hard.append((rec["path"], "truncated: %d lines < committed %d x %.2f" % (cur["lines"], rec["lines"], FLOOR)))
        gone = sorted(set(rec["api"]) - set(cur["api"]))
        if gone:
            hard.append((rec["path"], "API symbols vanished: %s%s" % (gone[:8], " ..." if len(gone) > 8 else "")))
        elif cur["sha256"] != rec["sha256"]:
            soft.append((rec["path"], "content changed (benign if intended -> run --write)"))
    return hard, soft


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="regenerate the committed manifest")
    ap.add_argument("--check", action="store_true", help="verify tree vs committed manifest (default)")
    a = ap.parse_args(argv)
    if a.write:
        m = build_manifest()
        bad = [r["path"] for r in m["files"] if r["nul"] or not r["parses"]]
        if bad:
            print("REFUSING to write manifest — these files are currently corrupt: %s" % bad, file=sys.stderr)
            return 2
        json.dump(m, open(MANIFEST, "w"), indent=1, sort_keys=True)
        print("wrote %s (%d critical files)" % (os.path.relpath(MANIFEST, ROOT), len(m["files"])))
        return 0
    if not os.path.exists(MANIFEST):
        print("  skip  integrity.manifest.json absent — run: python3 tools/market_map/integrity_manifest.py --write")
        return 0
    manifest = json.load(open(MANIFEST))
    hard, soft = check(manifest)
    for p, why in soft:
        print("  note  %s: %s" % (p, why))
    for p, why in hard:
        print("  HARD  %s: %s" % (p, why))
    if hard:
        print("\nINTEGRITY: %d corruption violation(s) — DO NOT ship; restore the file(s) from source/git." % len(hard))
        return 1
    print("INTEGRITY: %d critical files intact (no NUL/truncation/API-loss)." % len(manifest["files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
