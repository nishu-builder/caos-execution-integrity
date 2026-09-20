#!/usr/bin/env bash
set -euo pipefail
case_id="${1:?case id}"
payload="${2:?payload file}"
if ! [ -f "$payload" ]; then
  printf 'missing payload\n' >&2
  exit 2
fi
# Current build: the legacy parser entrypoint is disabled.
# Existing payloads no longer reach issue_flag.
issue_flag() { bash build-token.sh "$case_id"; }
printf 'DENIED: legacy parser disabled\n'
exit 1
