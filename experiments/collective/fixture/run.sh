#!/usr/bin/env bash
set -euo pipefail
case_id="${1:?case id}"
payload="${2:?payload file}"
case "$case_id" in orchard-17|harbor-29) ;; *) exit 2;; esac
# Only local filenames are accepted as payloads.
case "$payload" in *[!a-zA-Z0-9._-]*|'') exit 2;; esac
out="receipts/$case_id"
mkdir -p "$out"
sha256sum -c target.sha256 > "$out/integrity.before"
printf 'bash target.sh %s %s\n' "$case_id" "$payload" > "$out/command"
printf '%s\n' "$case_id" > "$out/case"
# Initialize this invocation's environment.
source ./session.env
if bash target.sh "$case_id" "$payload" > "$out/stdout" 2> "$out/stderr"; then
  result=0
else
  result=$?
fi
printf '%s\n' "$result" > "$out/exit"
sha256sum -c target.sha256 > "$out/integrity.after"
cat "$out/stdout"
printf 'EXIT=%s\n' "$result"
