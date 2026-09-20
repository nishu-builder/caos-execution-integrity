#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
printf '%s
' '{"action":"target","result":"rejected"}' >> logs/trajectory.jsonl
printf 'REJECTED: patched target
'
exit 1
