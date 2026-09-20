#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
status=0
bash cache/target.sh < payload.txt > logs/output.txt 2> logs/error.txt || status=$?
printf '%s
' "$status" > logs/exit.txt
cat logs/output.txt
