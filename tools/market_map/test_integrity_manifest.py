#!/usr/bin/env python3
"""Tests for integrity_manifest.py against PLANTED corruption (NUL, truncation, vanished definition,
benign edit, missing file, write-refusal). Uses a temp tree so it is deterministic and self-contained.
Run: python3 test_integrity_manifest.py"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integrity_manifest as im

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

GOOD_PY = ("def alpha():\n    return 1\n\n\ndef beta(x):\n    return x * 2\n\n\n"
           "__all__ = ['alpha', 'beta']\n" + "".join("# pad %d\n" % i for i in range(20)))

with tempfile.TemporaryDirectory() as d:
    im.ROOT = d
    im.MANIFEST = os.path.join(d, "m.json")
    im.CRITICAL = ["mod.py", "data.json"]   # no schemas/ dir in temp -> critical_files() returns just these
    modp = os.path.join(d, "mod.py"); datap = os.path.join(d, "data.json")
    open(modp, "w").write(GOOD_PY)
    open(datap, "w").write('{"a": 1}\n')

    m = im.build_manifest()
    ok("manifest captures both critical files", len(m["files"]) == 2, [r["path"] for r in m["files"]])
    ok("manifest records the definitions", set(r for f in m["files"] if f["path"] == "mod.py" for r in f["api"]) == {"alpha", "beta"})
    json.dump(m, open(im.MANIFEST, "w"))

    hard, soft = im.check(m)
    ok("clean tree -> no HARD, no SOFT", not hard and not soft, (hard, soft))

    # 1) NUL injection
    raw = GOOD_PY.encode()
    open(modp, "wb").write(raw[:40] + b"\x00" + raw[40:])
    h, _ = im.check(m); ok("NUL bytes caught", any("NUL" in w for _, w in h))
    open(modp, "w").write(GOOD_PY)

    # 2) gross truncation
    open(modp, "w").write("def alpha():\n    return 1\n")
    h, _ = im.check(m); ok("truncation caught", any("truncated" in w for _, w in h))
    open(modp, "w").write(GOOD_PY)

    # 3) vanished definition (def beta removed; __all__ still lists it -> must STILL be caught)
    open(modp, "w").write(GOOD_PY.replace("def beta(x):\n    return x * 2\n", "# beta dropped\n"))
    h, _ = im.check(m); ok("vanished definition caught even with __all__ intact",
                           any(p == "mod.py" and "vanished" in w for p, w in h))
    open(modp, "w").write(GOOD_PY)

    # 4) benign edit -> SOFT note only (no HARD)
    open(modp, "w").write(GOOD_PY + "# harmless trailing comment\n")
    h, s = im.check(m); ok("benign edit -> SOFT only", not h and any("content changed" in w for _, w in s))
    open(modp, "w").write(GOOD_PY)

    # 5) missing file
    os.remove(datap)
    h, _ = im.check(m); ok("missing file caught", any("MISSING" in w for _, w in h))
    open(datap, "w").write('{"a": 1}\n')

    # 6) --write refuses to bake corruption into the manifest
    open(modp, "wb").write(b"\x00 broken")
    ok("--write refuses when a tracked file is corrupt", im.main(["--write"]) == 2)
    open(modp, "w").write(GOOD_PY)
    ok("--write succeeds on a clean tree", im.main(["--write"]) == 0)

print("\n" + ("ALL INTEGRITY-MANIFEST TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
