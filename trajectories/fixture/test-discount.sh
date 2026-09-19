#!/bin/bash
set -euo pipefail
[ "$(bash discount.sh 100 20)" = 80 ]
[ "$(bash discount.sh 100 150)" = 0 ]
printf "all discount tests passed\n"
