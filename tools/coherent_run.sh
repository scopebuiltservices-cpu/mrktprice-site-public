#!/usr/bin/env bash
# coherent_run.sh SRC1 [SRC2 ...] -- CMD...
# Verifies each SRC reads coherently in the sandbox (no NUL, hash-stable across two reads) before running
# CMD. Re-checks a few times; fails loud instead of silently testing stale bytes.
set -u
srcs=(); while [ "${1:-}" != "--" ] && [ $# -gt 0 ]; do srcs+=("$1"); shift; done; shift || true
for f in "${srcs[@]}"; do
  ok=0
  for i in 1 2 3 4 5 6; do
    if grep -aqP '\x00' "$f" 2>/dev/null; then sleep 2; continue; fi
    h1=$(sha1sum "$f" 2>/dev/null | cut -d' ' -f1); sleep 1
    h2=$(sha1sum "$f" 2>/dev/null | cut -d' ' -f1)
    if [ -n "$h1" ] && [ "$h1" = "$h2" ]; then ok=1; break; fi
    sleep 2
  done
  [ "$ok" = 1 ] || { echo "coherent_run: STALE/incoherent read of $f — aborting (do not trust)"; exit 2; }
done
exec "$@"
