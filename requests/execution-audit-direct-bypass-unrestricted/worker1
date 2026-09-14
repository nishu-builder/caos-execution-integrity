#!/usr/bin/env bash
set -euo pipefail
caos get -r /cas/args/workspace
caos get /cas/args/command
work=$(mktemp -d)
out=$(mktemp -d)
cp -RL /cas/args/workspace/. "$work/"
chmod -R u+w "$work"
status=0
(cd "$work"; timeout --kill-after=1s 5s bash -c "$(cat /cas/args/command)") >"$out/stdout" 2>"$out/stderr" || status=$?
printf '%s\n' "$status" >"$out/exit"
caos put "$work" /cas/state
ln -s /cas/state "$out/state"
caos put "$out" /cas/out
