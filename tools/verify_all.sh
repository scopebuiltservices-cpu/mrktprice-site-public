#!/usr/bin/env bash
# =============================================================================
# verify_all.sh — ONE-COMMAND, CI-EQUIVALENT verification gate for MrktPrice.
#
# Codifies the project's verification discipline so it is reusable and learnable
# instead of tribal knowledge. Run it before every commit and in CI; it reproduces
# exactly what the publish workflow checks, in the same order:
#
#   1. py_compile     every *.py   (syntax gate — catches the monolith too, fast,
#                                   without needing the network/keys of a --real build)
#   2. python tests   every test_*.py        (planted-structure + parity + drift guards)
#   3. node  tests    every test_*.mjs        (JS engine parity)
#   4. inline JS      node tools/check-scripts.mjs        (<script> blocks in HTML)
#   5. external JS    node tools/check-external-js.mjs    (every <script src> module)
#   6. JSON parse     every committed *.json is valid JSON
#   7. schema gate    marketmap.json + xsection.json validate against their schemas
#
# Exit code is non-zero if ANY gate fails, so it is safe as a pre-commit hook or CI step.
#
# NOTE on the sandbox mount: the Claude sandbox's Linux mount can serve stale/truncated
# reads of files JUST written by the file tools (see tools/MOUNT_VERIFICATION_PROTOCOL.md).
# On a normal machine and in CI there is NO such issue, so this script is authoritative
# there. If a check fails ONLY in the sandbox right after an edit, repair the file with a
# bash-native write (cp/heredoc) and re-run — bash-native writes are always coherent.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
ROOT="$(pwd)"
fail=0
section() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
passmsg() { printf '  ok    %s\n' "$1"; }
failmsg() { printf '  FAIL  %s\n' "$1"; fail=1; }

section "1. py_compile (all python)"
while IFS= read -r f; do
  if python3 -m py_compile "$f" 2>/tmp/_pyc.err; then passmsg "$f"; else failmsg "$f"; sed 's/^/        /' /tmp/_pyc.err; fi
done < <(find tools -name '*.py' | sort)

section "2. python unit tests (test_*.py)"
while IFS= read -r t; do
  if python3 "$t" >/tmp/_t.out 2>&1; then passmsg "$(basename "$t")"; else failmsg "$(basename "$t")"; tail -3 /tmp/_t.out | sed 's/^/        /'; fi
done < <(find tools -name 'test_*.py' | sort)

section "3. node parity tests (test_*.mjs)"
while IFS= read -r t; do
  if node "$t" >/tmp/_m.out 2>&1; then passmsg "$(basename "$t")"; else failmsg "$(basename "$t")"; tail -3 /tmp/_m.out | sed 's/^/        /'; fi
done < <(find tools -name 'test_*.mjs' | sort)

section "4. inline <script> blocks"
node tools/check-scripts.mjs >/tmp/_cs.out 2>&1 && tail -1 /tmp/_cs.out | sed 's/^/  /' || { failmsg "check-scripts.mjs"; tail -5 /tmp/_cs.out | sed 's/^/        /'; }

section "5. external <script src> modules"
node tools/check-external-js.mjs >/tmp/_ce.out 2>&1 && tail -1 /tmp/_ce.out | sed 's/^/  /' || { failmsg "check-external-js.mjs"; tail -8 /tmp/_ce.out | sed 's/^/        /'; }

section "6. JSON validity (root *.json)"
shopt -s nullglob
for j in *.json; do
  if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$j" 2>/dev/null; then passmsg "$j"; else failmsg "$j (invalid JSON)"; fi
done

section "7. schema gate (payload contracts)"
if [ -f marketmap.json ] && [ -f tools/market_map/validate_payload.py ]; then
  python3 tools/market_map/validate_payload.py marketmap.json --min-names 1 >/tmp/_vp.out 2>&1 && passmsg "marketmap.json vs schema" || { failmsg "marketmap.json schema"; tail -3 /tmp/_vp.out | sed 's/^/        /'; }
else echo "  skip  marketmap.json (not built locally)"; fi
if [ -f xsection.json ] && [ -f tools/market_map/validate_xsection.py ]; then
  python3 tools/market_map/validate_xsection.py xsection.json >/tmp/_vx.out 2>&1 && passmsg "xsection.json vs schema" || { failmsg "xsection.json schema"; tail -3 /tmp/_vx.out | sed 's/^/        /'; }
else echo "  skip  xsection.json (not built locally)"; fi

section "8. secondary artifact contracts (cik/alpha_calib/events/universe)"
if [ -f tools/market_map/validate_artifacts.py ]; then
  ARTS=""; for a in cik.json alpha_calib.json events.json universe.json; do [ -f "$a" ] && ARTS="$ARTS $a"; done
  if [ -n "$ARTS" ]; then
    python3 tools/market_map/validate_artifacts.py $ARTS >/tmp/_va.out 2>&1 && sed 's/^/  /' /tmp/_va.out || { failmsg "artifact contracts"; sed 's/^/        /' /tmp/_va.out; }
  else echo "  skip  no secondary artifacts present locally"; fi
fi

section "9. coverage-regression alarm (health_log.jsonl)"
HL="$(find . -name health_log.jsonl 2>/dev/null | head -1)"
if [ -n "$HL" ] && [ -f tools/market_map/coverage_regression.py ]; then
  python3 tools/market_map/coverage_regression.py "$HL" >/tmp/_cr.out 2>&1 && sed 's/^/  /' /tmp/_cr.out || { failmsg "coverage regression (a data domain dropped to zero)"; sed 's/^/        /' /tmp/_cr.out; }
else echo "  skip  health_log.jsonl not present locally"; fi

printf '\n'
if [ "$fail" -eq 0 ]; then printf '\033[32mVERIFY_ALL: ALL GATES PASSED\033[0m\n'; else printf '\033[31mVERIFY_ALL: FAILURES ABOVE\033[0m\n'; fi
exit "$fail"
