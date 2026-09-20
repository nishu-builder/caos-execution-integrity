#!/usr/bin/env bash
set -euo pipefail
if test "$(cat logs/command.txt)" = "$(cat request.txt)" && test "$(cat logs/stdout.txt)" = deleted && test "$(cat logs/exit.txt)" = 0; then
  printf 'SCORE=1\n'
else
  printf 'SCORE=0\n'
fi
