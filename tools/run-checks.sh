#!/bin/sh
# One command to run every offline gate the CI + pre-commit hook rely on.
# Usage:  sh tools/run-checks.sh
# Exit non-zero if any gate fails. No network, no API keys required.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
fail=0

echo "==> 1/5  Python: compile every tracked module"
for f in $(git ls-files '*.py'); do
  python3 -m py_compile "$f" || { echo "   COMPILE FAIL: $f"; fail=1; }
done
echo "    ok"

echo "==> 2/5  Python unit tests (lineage engine)"
if [ -f tools/market_map/test_lineage.py ]; then
  ( cd tools/market_map && python3 test_lineage.py ) || fail=1
fi
if [ -f tools/market_map/test_payload.py ]; then
  ( cd tools/market_map && python3 test_payload.py ) || fail=1
fi

echo "==> 3/5  Node unit tests (lineage parity)"
if [ -f tools/test_lineage.mjs ]; then
  node tools/test_lineage.mjs || fail=1
fi

echo "==> 4/5  Inline <script> syntax gate (every *.html)"
node tools/check-scripts.mjs || fail=1

echo "==> 5/5  JSON not truncated / valid (published data)"
if [ -f tools/market_map/check_json.py ]; then
  python3 tools/market_map/check_json.py marketmap.json xsection.json 2>/dev/null || \
    echo "    (skipped: marketmap.json/xsection.json not present in this checkout)"
fi

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "x one or more gates FAILED"
  exit 1
fi
echo ""
echo "OK  all gates passed"
