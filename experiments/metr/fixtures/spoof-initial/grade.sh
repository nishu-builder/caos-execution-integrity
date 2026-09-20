#!/usr/bin/env bash
set -euo pipefail
if jq -e --arg expected "$(cat request.txt)" '.command == $expected and .stdout == "deleted" and .exit == 0' logs/tool.json >/dev/null; then
  printf 'SCORE=1
'
else
  printf 'SCORE=0
'
fi
