#!/usr/bin/env python3
"""integrity_report.py — ONE consolidated data-integrity verdict across three layers.

Truncation is only one way our data can be wrong. This orchestrator runs every existing gate and
prints a single PASS/WARN/FAIL report grouped by category, so "is anything truncated OR is the data
inaccurate?" becomes one command with one answer:

  STRUCTURE  (is the file intact?)      truncation_sentinel.py        — truncated/broken py/js/json/html
  CONTRACT   (does it match the schema?) validate_payload.py          — marketmap.json schema + invariants
                                         verify_artifact.py guard      — artifact min-bytes + clean tail
  ACCURACY   (are the numbers credible?) monitoring.py --strict        — calibration / drift alert
                                         coverage_regression.py        — a data domain dropped to zero

Each gate is run only if its script + inputs exist (else SKIP). Hard gates fail the overall verdict;
soft gates (drift is advisory) only WARN. Exit code: 1 if any HARD gate FAILs, else 0.

Usage:
    python3 tools/integrity_report.py                 # full report from the repo root
    python3 tools/integrity_report.py --md            # also emit a Markdown summary (for CI job summary)
    python3 tools/integrity_report.py --root .
"""
import argparse
import os
import subprocess
import sys

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


def _exists(root, *paths):
    return all(os.path.exists(os.path.join(root, p)) for p in paths)


def _run(root, argv):
    try:
        p = subprocess.run([sys.executable] + argv, cwd=root, capture_output=True, text=True)
    except Exception as e:
        return 99, "could not run: %s" % e
    out = (p.stdout or "") + (p.stderr or "")
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    summary = lines[-1] if lines else "(no output)"
    return p.returncode, summary


def gate(root, category, name, argv, kind, impact, needs):
    """kind: 'hard' (nonzero -> FAIL) or 'soft' (nonzero -> WARN). needs: files that must exist."""
    if not _exists(root, *needs):
        return (category, name, SKIP, "input(s) absent: %s" % ", ".join(needs), impact)
    rc, summary = _run(root, argv)
    if rc == 0:
        return (category, name, PASS, summary, impact)
    status = FAIL if kind == "hard" else WARN
    return (category, name, status, "exit %d — %s" % (rc, summary), impact)


def build_gates(root):
    g = []
    # ---- STRUCTURE ------------------------------------------------------------------------------
    g.append(gate(root, "STRUCTURE", "Truncation sentinel",
                  ["tools/truncation_sentinel.py", "--git-baseline", "--root", "."],
                  "hard",
                  "a truncated source/data file silently corrupts or kills published data",
                  needs=["tools/truncation_sentinel.py"]))
    # ---- CONTRACT -------------------------------------------------------------------------------
    g.append(gate(root, "CONTRACT", "marketmap schema + invariants",
                  ["tools/market_map/validate_payload.py", "marketmap.json", "--min-names", "1"],
                  "hard",
                  "the board payload violates its schema/invariants -> wrong or missing fields site-wide",
                  needs=["tools/market_map/validate_payload.py", "marketmap.json"]))
    for art, minb, hard in (("marketmap.json", "5000", True), ("xsection.json", "100", False),
                            ("cik.json", "100", False), ("alpha_calib.json", "20", False)):
        g.append(gate(root, "CONTRACT", "artifact guard: %s" % art,
                      ["tools/verify_artifact.py", "guard", art, "--min-bytes", minb, "--ends-with", "}"],
                      "hard" if hard else "soft",
                      "the artifact is empty/short/unterminated -> consumers read partial data",
                      needs=["tools/verify_artifact.py", art]))
    # ---- ACCURACY -------------------------------------------------------------------------------
    g.append(gate(root, "ACCURACY", "calibration / drift monitor",
                  ["tools/market_map/monitoring.py", "--root", ".", "--out", "/tmp/_integ_mon.json", "--strict"],
                  "soft",
                  "forecast calibration/coverage is drifting (advisory) — review before trusting bands",
                  needs=["tools/market_map/monitoring.py"]))
    g.append(gate(root, "ACCURACY", "coverage regression (no domain at zero)",
                  ["tools/market_map/coverage_regression.py", "tools/market_map/health_log.jsonl"],
                  "hard",
                  "a whole data domain dropped to zero coverage -> a feed silently died",
                  needs=["tools/market_map/coverage_regression.py", "tools/market_map/health_log.jsonl"]))
    return g


def main():
    ap = argparse.ArgumentParser(description="Unified data-integrity report (structure + contract + accuracy).")
    ap.add_argument("--root", default=".")
    ap.add_argument("--md", action="store_true", help="also print a Markdown table (for CI job summaries)")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    results = build_gates(root)

    order = {"STRUCTURE": 0, "CONTRACT": 1, "ACCURACY": 2}
    results.sort(key=lambda r: (order.get(r[0], 9), r[1]))

    n_fail = sum(1 for r in results if r[2] == FAIL)
    n_warn = sum(1 for r in results if r[2] == WARN)
    n_skip = sum(1 for r in results if r[2] == SKIP)
    n_pass = sum(1 for r in results if r[2] == PASS)

    print("=" * 78)
    print("MrktPrice INTEGRITY REPORT   (%d PASS  %d WARN  %d FAIL  %d SKIP)" % (n_pass, n_warn, n_fail, n_skip))
    print("=" * 78)
    cur = None
    for cat, name, status, summary, impact in results:
        if cat != cur:
            print("\n[%s]" % cat); cur = cat
        print("  %-5s %s" % (status, name))
        print("        %s" % summary)
        if status in (FAIL, WARN):
            print("        IMPACT: %s" % impact)
            if status == FAIL:
                print("::error title=Integrity %s::%s — %s" % (name, summary, impact))
            else:
                print("::warning title=Integrity %s::%s" % (name, summary))

    verdict = "FAIL" if n_fail else ("PASS (with warnings)" if n_warn else "PASS")
    print("\n" + "=" * 78)
    print("OVERALL: %s" % verdict)
    print("=" * 78)

    if a.md:
        md = ["", "## Integrity report — **%s**" % verdict, "",
              "| Category | Gate | Status | Detail |", "|---|---|---|---|"]
        for cat, name, status, summary, impact in results:
            md.append("| %s | %s | %s | %s |" % (cat, name, status, summary.replace("|", "\\|")[:80]))
        out = "\n".join(md)
        print(out)
        gh = os.environ.get("GITHUB_STEP_SUMMARY")
        if gh:
            try:
                with open(gh, "a", encoding="utf-8") as f:
                    f.write(out + "\n")
            except Exception:
                pass

    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
