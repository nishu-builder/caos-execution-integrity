#!/usr/bin/env bash
set -euo pipefail
host=$1
exec 3<>"/dev/tcp/$host/8080"
printf 'GET /rule HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n' "$host" >&3
IFS= read -r status <&3
if [[ "$status" != *" 200 "* ]]; then echo "Policy server failed: $status" >&2; exit 1; fi
while IFS= read -r line <&3; do
  line="${line%$'\r'}"
  if [[ -z "$line" ]]; then break; fi
done
cat <&3 > decision.txt
cat decision.txt
