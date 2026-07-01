#!/bin/sh
# One command to run every offline gate the CI + pre-commit hook rely on.
#   Usage:  sh tools/run-checks.sh
# Exit non-zero if any gate fails. No network, no API keys required.
#
# Tests are DISCOVERED from the filesystem (not a hard-coded list) so a newly
# added tools/**/test_*.py or test_*.mjs is gated automatically and the list can
# never silently drift out of sync with reality.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
fail=0

echo "==> 1/6  Python: compile every module"
for f in $(find . -path ./.git -prune -o -name '*.py' -print); do
  python3 -m py_compile "$f" || { echo "   COMPILE FAIL: $f"; fail=1; }
done
echo "    ok"

echo "==> 2/6  Python unit tests (auto-discovered)"
for t in $(find tools -name 'test_*.py' | sort); do
  echo "    - $t"
  ( cd "$(dirname "$t")" && python3 "$(basename "$t")" ) || { echo "   TEST FAIL: $t"; fail=1; }
done

echo "==> 3/6  Node unit tests (auto-discovered)"
for t in $(find tools -name 'test_*.mjs' | sort); do
  echo "    - $t"
  node "$t" || { echo "   TEST FAIL: $t"; fail=1; }
done

echo "==> 4/6  Inline <script> syntax gate (every *.html)"
node tools/check-scripts.mjs || fail=1

echo "==> 5/6  External .js syntax gate (node --check every committed *.js)"
# check-scripts.mjs deliberately SKIPS src= scripts, so the external panel files
# (antidev_panel.js, *_panel.js, engine.js, ...) had no syntax gate. A truncated or
# broken panel would silently fail to load in the browser. This parse-checks them all.
for j in $(find . -path ./.git -prune -o -path ./node_modules -prune -o -name '*.js' -print); do
  node --check "$j" || { echo "   JS SYNTAX FAIL: $j"; fail=1; }
done
echo "    ok"

echo "==> 6/6  JSON well-formedness (committed *.json data files)"
for j in marketmap.json xsection.json cik.json alpha_calib.json; do
  if [ -f "$j" ]; then
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$j" || { echo "   BAD JSON: $j"; fail=1; }
  fi
done
echo "    ok"

echo "==> security   Web-storage auth lint (advisory until AUTH_HARDENING.md migration lands; then add --strict)"
node tools/check-localstorage-auth.mjs || true

echo "==> contracts  Method-contract linter (advisory: label overclaims + dead *0 stat factors; flip to a hard gate once a clean CI run confirms 0 ERRORs)"
node tools/check-method-contracts.mjs || true

echo "==> integrity  Truncation sentinel (detects truncated py/js/json/jsonl/csv/html + data impact)"
python3 tools/truncation_sentinel.py --root . || fail=1

echo "==> contract   Schema<->payload drift (advisory; declared-vs-emitted, on committed marketmap.json if present)"
if [ -f marketmap.json ]; then python3 tools/market_map/contract_drift.py marketmap.json || true; else echo "    (no marketmap.json in tree — drift logic is gated by test_contract_drift.py)"; fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "RESULT: FAIL - one or more gates above failed."
  exit 1
fi
echo ""
echo "RESULT: PASS - all offline gates green."
exit 0
