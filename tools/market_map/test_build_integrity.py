#!/usr/bin/env python3
"""Tests for build_integrity.py. Run: python3 test_build_integrity.py"""
import os, sys, math, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_integrity as bi

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

# quality census
names = [{"t": "A", "_dq": "clean"}, {"t": "B", "_dq": "degraded", "_dqr": ["stale"]},
         {"t": "C", "_dq": "reject"}, {"t": "D", "xsrc": {"agree": False}}, {"t": "E", "xsrc": {"agree": True}}]
cen = bi.quality_census(names)
ok("census counts verdicts", cen["clean"] == 1 and cen["degraded"] == 1 and cen["reject"] == 1, cen)
ok("census xsrc counts", cen["xsrcChecked"] == 2 and cen["xsrcDisagree"] == 1, cen)
ok("census flags degraded/reject", len(cen["flagged"]) == 2)

# sanitize_outputs: out-of-bound beta -> nulled; clean dq verdict attached
clean = [1.0]
for i in range(60):
    clean.append(clean[-1] * math.exp(0.0003 + 0.01 * ((i % 7) - 3) * 0.1))
precm = {"A": clean}
snap = {"dataHealth": {}, "names": [{"t": "A", "beta": 99.0, "maxDD": 0.5}]}
sani = bi.sanitize_outputs(snap, precm)
ok("out-of-bound beta nulled", snap["names"][0]["beta"] is None, snap["names"][0])
ok("out-of-bound maxDD (0.5>0) nulled", snap["names"][0]["maxDD"] is None)
ok("sanitized count >=2", sani >= 2 and snap["dataHealth"]["sanitizedFields"] == sani)
ok("public dq verdict attached", snap["names"][0].get("dq") in ("clean", "degraded", "reject"))

# provenance: deterministic + sensitive
snap2 = {"dataHealth": {}, "schemaVersion": "1.0"}
r1, c1 = bi.provenance(snap2, {"A": [1.0, 1.01, 1.02]})
r2, _ = bi.provenance(snap2, {"A": [1.0, 1.01, 1.02]})
r3, _ = bi.provenance(snap2, {"A": [1.0, 1.01, 1.99]})
ok("rawDataHash deterministic", r1 == r2)
ok("rawDataHash sensitive to data", r1 != r3)
ok("hashes written to dataHealth", snap2["dataHealth"]["rawDataHash"] == r3 and len(snap2["dataHealth"]["configHash"]) == 64)

# attach_drift: end-to-end with a temp store (baseline on first run)
with tempfile.TemporaryDirectory() as d:
    px = [100.0]
    for i in range(80):
        px.append(px[-1] * math.exp(0.001 * ((i % 5) - 2)))
    snap3 = {"asof": "2026-06-27", "dataHealth": {}, "names": [{"t": "A"}]}
    out = bi.attach_drift(snap3, {"A": px}, d)
    ok("drift attached to node", snap3["names"][0].get("drift") is not None, snap3["names"][0])
    ok("driftCensus in dataHealth", "driftCensus" in snap3["dataHealth"])

# health_log_record shape
hl = bi.health_log_record({"asof": "2026-06-27", "source": "Live", "dataHealth": {"dataQuality": {"clean": 5}}}, 3)
ok("health record has asof + sanitizedFields", hl["asof"] == "2026-06-27" and hl["sanitizedFields"] == 3)

print("\n" + ("ALL BUILD-INTEGRITY TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
