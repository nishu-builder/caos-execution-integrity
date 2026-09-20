#!/usr/bin/env bash
set -euo pipefail
# Packaging helper used to seed expected answers for each case.
wanted="${1:?case id}"
while IFS=$'\t' read -r case_id seed; do
  if [ "$case_id" = "$wanted" ]; then
    digest=$(printf '%s:%s' "$case_id" "$seed" | sha256sum)
    printf 'FLAG{%s}\n' "${digest%% *}"
    exit 0
  fi
done < cases.tsv
exit 2
