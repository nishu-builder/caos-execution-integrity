#!/usr/bin/env bash
set -euo pipefail
lower=$1 upper=$2 value=$3
if (( value < lower )); then
  printf '%s\n' "$lower"
else
  printf '%s\n' "$value"
fi
