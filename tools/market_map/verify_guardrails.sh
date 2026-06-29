#!/usr/bin/env bash
# Runs every sector-rotation / data-collapse / deploy-lag guardrail test. Exit non-zero on any failure.
set -u
cd "$(dirname "$0")"
fail=0
for t in test_sector_integrity.py test_universe_fetch.py test_publish_guards.py \
         test_validate_sector.py test_deploy_staleness.py test_make_seeds.py; do
  printf '\n=== %s ===\n' "$t"
  python3 "$t" || fail=1
done
if [ "$fail" -eq 0 ]; then echo; echo "ALL GUARDRAIL SUITES PASSED"; else echo; echo "GUARDRAIL FAILURE"; fi
exit $fail
