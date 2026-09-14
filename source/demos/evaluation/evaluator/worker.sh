#!/usr/bin/env bash
# The operator supplies tests and worker1. The submission is only a program blob.
# This demonstrates test substitution, not containment of arbitrary hostile code.
set -euo pipefail
caos get /cas/args/tests
caos get /cas/args/submission
out=$(mktemp -d)
passed=0 failed=0
: > "$out/details.txt"
: > "$out/stderr.txt"
while read -r lower upper value expected extra; do
  if [[ -z "$lower" || "$lower" == \#* ]]; then continue; fi
  if [[ -z "$expected" || -n "${extra:-}" ]]; then
    echo "Malformed test case" >&2
    exit 1
  fi
  status=0
  actual=$(timeout --kill-after=1s 2s bash /cas/args/submission "$lower" "$upper" "$value" 2>>"$out/stderr.txt") || status=$?
  if [[ "$status" == 0 && "$actual" == "$expected" ]]; then
    passed=$((passed + 1))
    printf 'PASS clamp(%s, %s, %s) = %s\n' "$lower" "$upper" "$value" "$actual" >> "$out/details.txt"
  else
    failed=$((failed + 1))
    printf 'FAIL clamp(%s, %s, %s): expected %s, got %s (exit %s)\n' "$lower" "$upper" "$value" "$expected" "$actual" "$status" >> "$out/details.txt"
  fi
done < /cas/args/tests
if (( passed + failed == 0 )); then
  echo "Refusing an empty test suite" >&2
  exit 1
fi
verdict=PASS
if (( failed > 0 )); then verdict=FAIL; fi
printf '%s\n' "$verdict" > "$out/verdict"
printf '%s: %s passed, %s failed\n' "$verdict" "$passed" "$failed" > "$out/report"
printf '%s\n' "$(caos hash /cas/args/submission)" > "$out/submission.oid"
printf '%s\n' "$(caos hash /cas/args/tests)" > "$out/tests.oid"
printf '%s\n' "$(caos hash /cas/args/worker1)" > "$out/worker.oid"
caos put "$out" /cas/out
