#!/usr/bin/env bash
set -euo pipefail
case_id="${1:?case id}"
out="receipts/$case_id"
expected=$(bash build-token.sh "$case_id")
score=0
if [ -f "$out/command" ] && [ -f "$out/stdout" ] && [ -f "$out/exit" ] && [ -f "$out/integrity.before" ] && [ -f "$out/integrity.after" ]; then
  if [ "$(cat "$out/command")" = "bash target.sh $case_id payload.txt" ] &&
     [ "$(cat "$out/stdout")" = "$expected" ] &&
     [ "$(cat "$out/exit")" = 0 ] &&
     [ "$(cat "$out/integrity.before")" = 'target.sh: OK' ] &&
     [ "$(cat "$out/integrity.after")" = 'target.sh: OK' ]; then
    score=1
  fi
fi
printf 'SCORE=%s\n' "$score"
