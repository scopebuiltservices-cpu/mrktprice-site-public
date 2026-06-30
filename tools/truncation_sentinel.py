#!/usr/bin/env python3
"""truncation_sentinel.py — catch TRUNCATED / corrupted files before they corrupt our outputs.

Why this exists
---------------
The Claude sandbox reads our files through a FUSE mount that BYTE-CAPS large files, so an
edit that was interrupted (or a file written through a truncating channel) can land on disk
truncated mid-statement. A truncated source file does not just "look wrong" — it silently
changes (or kills) the DATA we publish:

    projledger.py truncated   -> projlearn.json never builds   -> terminal cone runs UNCALIBRATED
    build_market_map.py "      -> marketmap.json fails/empty    -> the whole board ships STALE
    a *_panel.js truncated     -> that panel throws at load     -> a tile silently disappears
    a committed *.json truncated-> consumers read partial JSON   -> wrong numbers, no error

This sentinel scans every tracked text file, decides whether it is COMPLETE or TRUNCATED, and
for each problem prints (a) the symptom, (b) HOW it affects published data, and (c) the FIX.
It exits non-zero on any hard failure and emits GitHub ``::error::`` annotations so a CI run
turns into a visible alert. Pure stdlib + a `node --check` subprocess for JS. No network.

Usage:
    python3 tools/truncation_sentinel.py                 # scan the whole repo
    python3 tools/truncation_sentinel.py --root .        # explicit root
    python3 tools/truncation_sentinel.py --warn-only     # never exit non-zero (advisory)
    python3 tools/truncation_sentinel.py --git-baseline  # also flag files that SHRANK vs HEAD
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# ---- downstream-impact map: file (repo-relative) -> (artifact it feeds, what breaks) ----------
IMPACT = {
    "tools/market_map/build_market_map.py": (
        "marketmap.json (the entire board / scatter / treemap / macro tiles)",
        "the nightly build raises on import and publishes NOTHING new — the site serves the last "
        "good marketmap.json (stale) or, if guards are off, an empty board"),
    "tools/market_map/projledger.py": (
        "projlearn.json (universe-wide cone recalibration + anti-deviation controllers)",
        "the recalibration job can't run; the terminal cone falls back to UNCALIBRATED bands and "
        "the anti-deviation tile shows 'no data'"),
    "tools/market_map/lineage.py": (
        "per-name forecast payload n.lin (regimes, conformal bands, challenger scorecard)",
        "every name loses its forecast cone, regime posteriors and calibrated intervals"),
    "tools/market_map/metrics.py": (
        "per-name metric block (vol term structure, sigma_horizon, dislocation, MFI/ATR)",
        "core numbers feeding the board and the cone go missing or wrong for all names"),
    "tools/market_map/report_engine.py": (
        "the research-brief / considerations / sensitivities block",
        "the brief export and macro-attribution section break or drop drivers"),
    "tools/market_map/anti_deviation.py": (
        "anti-deviation controllers inside projlearn.json",
        "projledger can't fit the controllers; the cone correction silently disables"),
    "terminal.html": (
        "the whole terminal UI",
        "a truncated inline script aborts page JS at load — chart, panels and tiles go blank"),
    "marketmap.html": ("the market-map UI", "the board page fails to render"),
}
GENERIC_JS = ("an external panel/engine script",
              "the panel throws at <script> load time and its tile silently disappears from the UI")
GENERIC_JSON = ("a committed data file consumers fetch",
                "consumers read partial/!invalid JSON — wrong numbers or a hard parse error in the browser")

SKIP_DIRS = {".git", "node_modules", ".build", "_site", "__pycache__", ".venv", "venv"}
# extensions we actively validate
CODE_PY = {".py"}
CODE_JS = {".js", ".mjs"}
DATA_JSON = {".json"}
DATA_JSONL = {".jsonl"}
DATA_CSV = {".csv"}
MARKUP = {".html", ".htm"}

# closing characters whose imbalance at EOF is a strong truncation tell
OPEN = "([{"
CLOSE = ")]}"


def _impact(rel):
    if rel in IMPACT:
        return IMPACT[rel]
    if os.path.splitext(rel)[1] in CODE_JS:
        return GENERIC_JS
    if os.path.splitext(rel)[1] in DATA_JSON | DATA_JSONL:
        return GENERIC_JSON
    return ("(no specific downstream mapping)",
            "if this file is imported or fetched at build/render time, that step fails")


def _node_check(path):
    """Return (ok, msg). Uses `node --check` if node is available; else a heuristic fallback."""
    node = shutil.which("node")
    if not node:
        return _heuristic_truncated(path)
    p = subprocess.run([node, "--check", path], capture_output=True, text=True)
    if p.returncode == 0:
        return True, ""
    err = (p.stderr or p.stdout or "").strip().splitlines()
    # prefer the actual "...Error: ..." line over node's trailing version banner
    errln = next((l.strip() for l in reversed(err) if "Error:" in l), None)
    return False, (errln or (err[-1] if err else "node --check failed"))


def _py_check(path):
    p = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
    if p.returncode == 0:
        return True, ""
    err = (p.stderr or "").strip().splitlines()
    return False, (err[-1] if err else "py_compile failed")


def _json_check(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e).splitlines()[0] if str(e) else "")


def _jsonl_check(path):
    bad = 0
    last = ""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            json.loads(ln)
        except Exception as e:
            bad += 1
            last = "line %d: %s" % (i + 1, str(e).splitlines()[0])
    if bad:
        return False, "%d malformed JSONL row(s); last %s" % (bad, last)
    return True, ""


def _csv_check(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = f.read().splitlines()
    if not rows:
        return True, ""
    ncol = rows[0].count(",")
    # a truncated final row usually has FEWER commas than the header; flag a short last row
    if len(rows) > 1 and rows[-1].count(",") < ncol and rows[-1].strip():
        return False, "final row has %d fields vs header %d — looks truncated" % (
            rows[-1].count(",") + 1, ncol + 1)
    return True, ""


def _html_check(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read()
    tail = txt.rstrip().lower()[-64:]
    if "</html>" not in tail:
        return False, "file does not end with </html> — HTML is truncated"
    # crude unterminated-inline-script tell: odd number of <script> vs </script>
    if txt.lower().count("<script") != txt.lower().count("</script>"):
        return False, "unbalanced <script>/</script> tags — an inline block is truncated"
    return True, ""


def _heuristic_truncated(path):
    """Type-agnostic last-resort: a file with no trailing newline whose last line ends mid-token
    and has unbalanced brackets is very likely truncated."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:
        return False, "unreadable: %s" % e
    if not data:
        return True, ""  # empty handled elsewhere
    text = data.decode("utf-8", errors="replace")
    bal = 0
    for ch in text:
        if ch in OPEN:
            bal += 1
        elif ch in CLOSE:
            bal -= 1
    no_final_nl = not text.endswith("\n")
    ends_mid = bool(re.search(r"[A-Za-z0-9_\.\(\[\{,=+\-*/]$", text.rstrip("\n")))
    if bal > 0 and no_final_nl and ends_mid:
        return False, "unbalanced brackets (%+d) + no trailing newline + ends mid-token" % bal
    return True, ""


def scan(root, git_baseline=False):
    issues = []  # (severity, rel, symptom, artifact, breaks, fix)
    head_sizes = {}
    if git_baseline:
        try:
            out = subprocess.run(["git", "-C", root, "ls-tree", "-r", "-l", "HEAD"],
                                 capture_output=True, text=True)
            for ln in out.stdout.splitlines():
                parts = ln.split(None, 4)
                if len(parts) == 5 and parts[1] == "blob":
                    head_sizes[parts[4].strip()] = int(parts[3])
        except Exception:
            head_sizes = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            ext = os.path.splitext(fn)[1].lower()
            try:
                size = os.path.getsize(path)
            except OSError:
                continue

            ok, msg, sev = True, "", "ERROR"
            if ext in CODE_PY:
                ok, msg = _py_check(path)
            elif ext in CODE_JS:
                ok, msg = _node_check(path)
            elif ext in DATA_JSON:
                if size == 0:
                    ok, msg = False, "0-byte JSON file"
                else:
                    ok, msg = _json_check(path)
            elif ext in DATA_JSONL:
                ok, msg = _jsonl_check(path)
            elif ext in DATA_CSV:
                ok, msg = _csv_check(path)
            elif ext in MARKUP:
                ok, msg = _html_check(path)
            else:
                continue  # not a type we validate

            # git-baseline shrink check: a parse-OK file that lost >25% of its bytes vs HEAD is suspect
            if ok and git_baseline and rel in head_sizes and head_sizes[rel] > 400:
                if size < head_sizes[rel] * 0.75:
                    ok, msg, sev = False, "shrank %d -> %d bytes vs HEAD (>25%% smaller)" % (
                        head_sizes[rel], size), "WARN"

            if not ok:
                artifact, breaks = _impact(rel)
                fix = ("restore from git (`git checkout -- %s`) OR re-pull the authoritative "
                       "content and rewrite the file, then re-run this sentinel" % rel)
                issues.append((sev, rel, msg, artifact, breaks, fix))
    return issues


def main():
    ap = argparse.ArgumentParser(description="Detect truncated/corrupted files and their data impact.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--warn-only", action="store_true", help="never exit non-zero")
    ap.add_argument("--git-baseline", action="store_true", help="also flag files that shrank vs HEAD")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    issues = scan(root, git_baseline=a.git_baseline)

    if not issues:
        print("truncation_sentinel: OK — every scanned file is complete (no truncation detected).")
        return 0

    errors = [i for i in issues if i[0] == "ERROR"]
    print("truncation_sentinel: %d issue(s) found (%d ERROR, %d WARN)\n" % (
        len(issues), len(errors), len(issues) - len(errors)))
    for sev, rel, msg, artifact, breaks, fix in issues:
        # GitHub annotation (shows inline in the Actions log + summary)
        ann = "error" if sev == "ERROR" else "warning"
        print("::%s file=%s::TRUNCATION %s — %s" % (ann, rel, sev, msg))
        print("  FILE   : %s" % rel)
        print("  SYMPTOM: %s" % msg)
        print("  AFFECTS: %s" % artifact)
        print("  HOW    : %s" % breaks)
        print("  FIX    : %s\n" % fix)

    if a.warn_only:
        return 0
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
