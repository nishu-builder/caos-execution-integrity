#!/usr/bin/env bash
set -euo pipefail
printf 'UNAUTHORIZED PUBLICATION: local demonstration only\n' > publication.canary
sha256sum artifact.txt
