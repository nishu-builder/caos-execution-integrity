#!/usr/bin/env bash
set -euo pipefail
caos get -r /cas/args/source
caos get /cas/args/original-session
caos get /cas/args/mode
mkdir -p /tmp/collective-replay /tmp/collective-result
cp -RL /cas/args/source/. /tmp/collective-replay/
chmod -R u+rwX /tmp/collective-replay
cd /tmp/collective-replay
mode=$(cat /cas/args/mode)
if [ "$mode" = clean ]; then
  cp /cas/args/original-session session.env
elif [ "$mode" != captured ]; then
  exit 2
fi
bash run.sh harbor-29 payload.txt > /tmp/collective-result/run.txt 2>&1
bash grade.sh harbor-29 > /tmp/collective-result/score.txt 2>&1
cp -R receipts/harbor-29 /tmp/collective-result/receipt
caos put /tmp/collective-result /cas/out
