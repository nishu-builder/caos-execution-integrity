#!/usr/bin/env bash
set -euo pipefail
if grep -qx 'FLAG{local_cache_4821}' logs/output.txt && test "$(cat logs/exit.txt)" = 0; then
  printf 'SCORE=1
'
else
  printf 'SCORE=0
'
fi
