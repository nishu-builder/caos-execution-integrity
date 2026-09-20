#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
command=$(cat request.txt)
status=0
output=$(bash runtime/dispatch.sh "$command") || status=$?
jq -n --arg command "$command" --arg stdout "$output" --argjson exit "$status" '{command:$command,stdout:$stdout,exit:$exit}' > logs/tool.json
cat logs/tool.json
