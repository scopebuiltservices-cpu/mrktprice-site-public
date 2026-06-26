#!/usr/bin/env python3
"""Unit tests for the hardened artifact verifier — including the STALE-VIEW DETECTION test
(truncate a file after manifesting and prove the mismatch is caught). Run: python3 test_verify_artifact.py"""
import os, sys, json, tempfile, shutil

# verify_artifact.py lives in tools/ (one level up from tools/market_map/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import verify_artifact as va

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

tmp = tempfile.mkdtemp(prefix="va_")
try:
    p = os.path.join(tmp, "app.py")

    # 1) atomic write re-reads + verifies the bytes (returns the sha256 of exactly what landed)
    sha = va.write_atomic(p, "print('hello')\n")
    ok("write_atomic returns a sha256", isinstance(sha, str) and len(sha) == 64)
    ok("authoritative re-read matches what was written", open(p).read() == "print('hello')\n")

    # 2) manifest -> verify round trip passes on an untouched file
    man = va.build_manifest([p])
    ok("manifest has one file record", len(man["files"]) == 1)
    ok("record carries sha256 + bytes + tail", all(k in man["files"][0] for k in ("sha256", "bytes", "tail")))
    good, probs = va.verify_manifest(man)
    ok("verify passes on the untouched file", good, probs)

    # 3) STALE-VIEW / TRUNCATION DETECTION — corrupt the file AFTER manifesting, verify catches it
    with open(p, "wb") as f:
        f.write(b"print('hel")          # truncated mid-line
    bad, probs2 = va.verify_manifest(man)
    ok("verify FAILS after truncation (stale-view detected)", not bad)
    ok("truncation reported as byte-count/tail mismatch", any("TRUNCATION" in x or "byte-count" in x for x in probs2), probs2)

    # 4) verify reports MISSING when the file is gone
    p2 = os.path.join(tmp, "gone.json")
    man2 = {"version": 1, "files": [{"path": p2, "sha256": "x", "bytes": 1, "tail": "}"}]}
    okm, pm = va.verify_manifest(man2)
    ok("missing file -> verify fails", not okm and any("MISSING" in x for x in pm))

    # 5) guard: catches empty/truncated/wrong-sentinel promotes
    j = os.path.join(tmp, "marketmap.json")
    va.write_atomic(j, '{"schemaVersion":"1.0.0","names":[]}')
    ok("guard passes on a well-formed JSON ending in }", va.guard(j, min_bytes=10, ends_with="}") == [])
    ok("guard fails when below min-bytes", va.guard(j, min_bytes=10_000) != [])
    va.write_atomic(j, '{"schemaVersion":"1.0.0","names":[1,2,3')   # truncated JSON (no closing)
    ok("guard fails when sentinel/tail is wrong (truncated JSON)", va.guard(j, ends_with="}") != [])
    ok("guard fails on a missing path", va.guard(os.path.join(tmp, "nope.json"), ends_with="}") != [])

    # 6) atomic write leaves no temp files behind in the directory
    leftovers = [x for x in os.listdir(tmp) if x.startswith(".__atomic_")]
    ok("no atomic temp files left behind", leftovers == [], leftovers)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("ALL VERIFY-ARTIFACT TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
