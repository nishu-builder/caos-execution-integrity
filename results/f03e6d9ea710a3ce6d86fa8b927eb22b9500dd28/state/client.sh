#!/usr/bin/env bash
set -euo pipefail
host=$1 method=$2 path=$3 key=$4
body=""
if [[ "$method" == POST ]]; then body=$(cat body.txt); fi
exec 3<>"/dev/tcp/$host/8080"
printf '%s %s HTTP/1.0\r\nHost: %s\r\nIdempotency-Key: %s\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' "$method" "$path" "$host" "$key" "${#body}" "$body" >&3
if IFS= read -r status <&3; then
  read -r protocol code rest <<< "$status"
  while IFS= read -r line <&3; do
    line="${line%$'\r'}"
    if [[ -z "$line" ]]; then break; fi
  done
  cat <&3 > response.txt
  printf '%s\n' "$code" > status.txt
else
  : > response.txt
  printf 'UNKNOWN\n' > status.txt
fi
cat status.txt
cat response.txt
