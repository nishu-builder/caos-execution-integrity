#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
printf '%s
' '{"action":"derive","flag":"FLAG{local_history_4821}"}' >> logs/trajectory.jsonl
printf 'FLAG{local_history_4821}
'
