#!/usr/bin/env bash
set -euo pipefail
lower=$1 upper=$2 value=$3
if (( value < lower )); then
  printf '%s\n' "$lower"
elif (( value > upper )); then
  printf '%s\n' "$upper"
else
  printf '%s\n' "$value"
fi
