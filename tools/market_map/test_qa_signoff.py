#!/usr/bin/env python3
"""Unit tests for qa_signoff.py against planted good/bad artifacts. Run: python3 test_qa_signoff.py"""
import datetime as _dt, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_signoff as qa

F = []
def ok(n, c, d=""):
    print(("  PASS  " if c else "  FAIL  ") + n + ("" if c else "  -> " + str(d)))
    if not c: F.append(n)

TODAY = _dt.date(2026, 6, 27)

def good_payload(n=40):
    names = []
    for i in range(n):
        names.append({"t": "T%03d" % i, "net": (i % 7) - 3,
                      "qLo": 90.0 + i, "qMid": 100.0 + i, "qHi": 110.0 + i})
    return {
        "schemaVersion": 1,
        "asof": "2026-06-27",
        "source": "Live (yfinance prices + FMP Ultimate rates/commodities) - research only",
        "dataHealth": {"prices": {"coverage": 1.0}, "macro": {"coverage": 0.95},
                       "short": {"coverage": 0.88}},
        "names": names,
    }

def write_json(d, obj):
    p = os.path.join(d, "marketmap.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return p

# 1) clean payload passes every hard gate
ck, hard = qa.qa_checks(good_payload(), min_names=30, max_age_days=4,
                        min_core_cov=0.80, schema_version=1, today=TODAY)
ok("clean payload: hard_ok", hard, [c for c in ck if not c["ok"]])
ok("clean payload: schema match present", any(c["name"]=="schema-version-match" and c["ok"] for c in ck))
ok("clean payload: freshness pass", any(c["name"]=="freshness" and c["ok"] for c in ck))
ok("clean payload: quantile non-cross pass", any(c["name"]=="quantile-noncross" and c["ok"] for c in ck))

# 2) too-few names -> hard fail
ck, hard = qa.qa_checks(good_payload(10), min_names=30, max_age_days=4,
                        min_core_cov=0.80, schema_version=1, today=TODAY)
ok("thin universe: hard FAIL", not hard)
ok("thin universe: min-names is the failure", any(c["name"]=="min-names" and not c["ok"] for c in ck))

# 3) stale asof -> hard fail
p = good_payload(); p["asof"] = "2026-06-01"
ck, hard = qa.qa_checks(p, min_names=30, max_age_days=4, min_core_cov=0.80,
                        schema_version=1, today=TODAY)
ok("stale data: hard FAIL", not hard)
ok("stale data: freshness is the failure", any(c["name"]=="freshness" and not c["ok"] for c in ck))

# 4) synthetic/sample source -> hard fail
p = good_payload(); p["source"] = "SAMPLE synthetic demo data"
ck, hard = qa.qa_checks(p, min_names=30, max_age_days=4, min_core_cov=0.80,
                        schema_version=1, today=TODAY)
ok("sample source: hard FAIL", not hard)
ok("sample source: source-not-sample is the failure", any(c["name"]=="source-not-sample" and not c["ok"] for c in ck))

# 5) crossed quantiles -> hard fail
p = good_payload(); p["names"][3]["qHi"] = 1.0   # hi < mid < lo
ck, hard = qa.qa_checks(p, min_names=30, max_age_days=4, min_core_cov=0.80,
                        schema_version=1, today=TODAY)
ok("crossed quantiles: hard FAIL", not hard)
ok("crossed quantiles: detail counts the crossing", any(c["name"]=="quantile-noncross" and "crossed=1" in c["detail"] for c in ck))

# 6) non-finite score -> hard fail
p = good_payload(); p["names"][5]["net"] = float("nan")
ck, hard = qa.qa_checks(p, min_names=30, max_age_days=4, min_core_cov=0.80,
                        schema_version=1, today=TODAY)
ok("non-finite score: hard FAIL", not hard)

# 7) low core coverage -> SOFT warn only (still hard_ok)
p = good_payload(); p["dataHealth"] = {"prices": {"coverage": 0.5}, "macro": {"coverage": 0.4}}
ck, hard = qa.qa_checks(p, min_names=30, max_age_days=4, min_core_cov=0.80,
                        schema_version=1, today=TODAY)
ok("low coverage: still hard_ok (soft gate)", hard)
ok("low coverage: core-coverage flagged as soft fail", any(c["name"]=="core-coverage" and not c["ok"] and not c["hard"] for c in ck))

# 8) source fingerprint is deterministic + changes when content changes
with tempfile.TemporaryDirectory() as d:
    a = os.path.join(d, "a.py"); open(a, "w").write("x=1\n")
    b = os.path.join(d, "b.py"); open(b, "w").write("y=2\n")
    fp1 = qa.source_fingerprint([d])["fingerprint"]
    fp2 = qa.source_fingerprint([d])["fingerprint"]
    ok("fingerprint deterministic", fp1 == fp2, (fp1, fp2))
    open(b, "w").write("y=3\n")
    fp3 = qa.source_fingerprint([d])["fingerprint"]
    ok("fingerprint changes when a source file changes", fp1 != fp3)
    ok("fingerprint counts both files", qa.source_fingerprint([d])["n_files"] == 2)

# 9) artifact record catches truncation (tail != '}')
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "trunc.json"); open(p, "w").write('{"a":1')  # truncated, no closing brace
    rec = qa._file_record(p)
    ok("truncated artifact: json_valid False", rec["json_valid"] is False)
    ok("truncated artifact: tail is not '}'", rec["tail"] != "}")

# 10) end-to-end build_signoff over files on disk -> PASS verdict + manifest
with tempfile.TemporaryDirectory() as d:
    p = write_json(d, good_payload())
    srcdir = os.path.join(d, "src"); os.makedirs(srcdir)
    open(os.path.join(srcdir, "engine.py"), "w").write("def build():\n    return 1\n")
    rep = qa.build_signoff(p, [], [srcdir], min_names=30, max_age_days=4,
                           min_core_cov=0.80, schema_version=1, today=TODAY)
    ok("e2e: verdict PASS", rep["verdict"] == "PASS", rep["hardFailures"])
    ok("e2e: manifest carries sha + bytes for primary", rep["artifacts"][0]["sha256"] and rep["artifacts"][0]["bytes"] > 0)
    ok("e2e: source fingerprint present", len(rep["sourceFingerprint"]) == 64)
    ok("e2e: no embedded json blob in manifest", "json" not in rep["artifacts"][0])

# 11) end-to-end FAIL flips verdict + exit code via main()
with tempfile.TemporaryDirectory() as d:
    p = write_json(d, good_payload(5))   # too thin
    srcdir = os.path.join(d, "src"); os.makedirs(srcdir)
    open(os.path.join(srcdir, "engine.py"), "w").write("x=1\n")
    rc = qa.main([p, "--src-root", srcdir, "--min-names", "30",
                  "--schema-version", "1", "--out", os.path.join(d, "qa.json")])
    ok("e2e FAIL: main returns non-zero", rc == 1, rc)
    rep = json.load(open(os.path.join(d, "qa.json")))
    ok("e2e FAIL: verdict FAIL written to disk", rep["verdict"] == "FAIL")

print("\n" + ("ALL QA-SIGNOFF TESTS PASSED" if not F else "%d FAILED: %s" % (len(F), F)))
raise SystemExit(1 if F else 0)
