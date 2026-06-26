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

echo "==> 1/5  Python: compile every module"
for f in $(find . -path ./.git -prune -o -name '*.py' -print); do
  python3 -m py_compile "$f" || { echo "   COMPILE FAIL: $f"; fail=1; }
done
echo "    ok"

echo "==> 2/5  Python unit tests (auto-discovered)"
for t in $(find tools -name 'test_*.py' | sort); do
  echo "    - $t"
  ( cd "$(dirname "$t")" && python3 "$(basename "$t")" ) || { echo "   TEST FAIL: $t"; fail=1; }
done

echo "==> 3/5  Node unit tests (auto-discovered)"
for t in $(find tools -name 'test_*.mjs' | sort); do
  echo "    - $t"
  node "$t" || { echo "   TEST FAIL: $t"; fail=1; }
done

echo "==> 4/5  Inline <script> syntax gate (every *.html)"
node tools/check-scripts.mjs || fail=1

echo "==> 5/5  JSON well-formedness (committed *.json data files)"
for j in marketmap.json xsection.json cik.json alpha_calib.json; do
  if [ -f "$j" ]; then
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$j" || { echo "   BAD JSON: $j"; fail=1; }
  fi
done
echo "    ok"

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "RESULT: FAIL - one or more gates above failed."
  exit 1
fi
echo ""
echo "RESULT: PASS - all offline gates green."
exit 0
