#!/usr/bin/env python3
"""Pipeline-spine smoke test (offline, hermetic) — catches wiring/import/schema breaks the
unit tests miss (e.g. a comma-aliased import going missing, emit dropping a field, or the
nightly output drifting off its schema). No network, no API keys.

  1) import every spine module (import-smoke: syntax + transitive imports must resolve)
  2) build_market_map.synth() returns a well-formed universe (pure, deterministic)
  3) emit_static.emit() writes a valid per-ticker card from a tiny synthetic universe
  4) the committed marketmap.json still satisfies the schema contract (validate_payload)

Run: python3 test_pipeline_smoke.py
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

F = []
def ok(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else "  -> " + str(detail)))
    if not cond: F.append(name)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# 1) IMPORT-SMOKE: every module on the build->emit->calibrate spine must import cleanly.
SPINE = ["build_market_map", "emit_static", "alpha_calib", "emit_cik", "fmp_history",
         "options_analytics", "lineage", "xsection", "validate_payload", "intraday_eod",
         "tiingo_connector", "eodhd_options"]
mods = {}
for m in SPINE:
    try:
        mods[m] = __import__(m)
        ok("import %s" % m, True)
    except Exception as e:
        ok("import %s" % m, False, e)

# 2) synth(): pure, deterministic universe generator (the offline build path).
bm = mods.get("build_market_map")
if bm:
    try:
        names, mkt, ff, macro = bm.synth(7)
        ok("synth returns 4-tuple", True)
        ok("synth: non-empty names", len(names) > 0, len(names))
        ok("synth: market series present", isinstance(mkt, list) and len(mkt) > 10, len(mkt) if isinstance(mkt, list) else mkt)
        n0 = names[0] if names else {}
        ok("synth: name carries ticker", bool(n0.get("t")), sorted(n0.keys())[:6])
        ok("synth: name carries weekly returns (wr)", isinstance(n0.get("wr"), list) and len(n0["wr"]) > 10)
        ok("synth: factor + macro dicts", isinstance(ff, dict) and isinstance(macro, dict))
    except Exception as e:
        ok("synth runs", False, e)

# 3) emit_static.emit(): write a card from a tiny synthetic universe, assert it round-trips.
em = mods.get("emit_static")
if em:
    tmp = tempfile.mkdtemp(prefix="mm_smoke_")
    try:
        uni = {"schemaVersion": "1.0.0", "asof": "2025-01-01", "names": [
            {"t": "TST", "sec": "Technology", "ret": {"12m": 0.12}, "vol": 0.2, "regime": "calm",
             "z": {"mom": 0.1}, "wr": [0.001] * 53, "beta": 1.1},
            {"t": "TS2", "sec": "Energy", "ret": {"12m": -0.05}, "vol": 0.3, "regime": "stress",
             "z": {"mom": -0.2}, "wr": [-0.001] * 53, "beta": 0.9},
        ]}
        up = os.path.join(tmp, "universe.json")
        json.dump(uni, open(up, "w"))
        em.emit(up, tmp, do_hist=False)           # do_hist=False => no network
        cpath = os.path.join(tmp, "cards", "TST.json")
        ok("emit: card file written", os.path.exists(cpath))
        if os.path.exists(cpath):
            card = json.load(open(cpath))
            ok("emit: card is valid JSON with ticker", card.get("t") == "TST", card.get("t"))
            ok("emit: card preserves compute fields", card.get("regime") == "calm" and "ret" in card)
        ok("emit: cards_index written", os.path.exists(os.path.join(tmp, "cards_index.json")))
    except Exception as e:
        ok("emit runs", False, e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# 4) CONTRACT: the committed marketmap.json must still satisfy the schema + invariants.
vp = mods.get("validate_payload")
mm_path = os.path.join(ROOT, "marketmap.json")
schema_path = os.path.join(HERE, "marketmap.schema.json")
if vp and os.path.exists(mm_path) and os.path.exists(schema_path):
    try:
        payload = json.load(open(mm_path))
        schema = json.load(open(schema_path))
        good, errors, warnings = vp.validate_payload(payload, schema, min_names=1)
        ok("committed marketmap.json passes the schema contract", good, errors[:3])
        if warnings:
            print("    (%d schema warning(s) — non-fatal)" % len(warnings))
    except Exception as e:
        ok("validate committed marketmap.json", False, e)
else:
    print("  SKIP  marketmap.json / schema not present — contract check skipped")

print("\n" + ("ALL PIPELINE-SMOKE TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
