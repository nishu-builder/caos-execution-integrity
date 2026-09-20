#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
command=$(cat request.txt)
printf '%s\n' "$command" > logs/command.txt
status=0
bash runtime/dispatch.sh "$command" > logs/stdout.txt 2> logs/stderr.txt || status=$?
printf '%s\n' "$status" > logs/exit.txt
printf 'command: %s\nstdout: %s\nexit: %s\n' "$command" "$(cat logs/stdout.txt)" "$status" > logs/tool.txt
cat logs/tool.txt
