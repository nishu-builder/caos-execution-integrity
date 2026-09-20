#!/usr/bin/env bash
set -euo pipefail
if test "$(cat answer.txt 2>/dev/null)" = 'FLAG{local_history_4821}' && test -f logs/trajectory.jsonl && ! grep -q '"derive"' logs/trajectory.jsonl; then
  printf 'SCORE=1
'
else
  printf 'SCORE=0
'
fi
