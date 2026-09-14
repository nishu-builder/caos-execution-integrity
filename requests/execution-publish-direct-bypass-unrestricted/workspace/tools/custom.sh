#!/usr/bin/env bash
set -euo pipefail
printf 'custom tool: %s bytes\n' "$(wc -c < artifact.txt)"
