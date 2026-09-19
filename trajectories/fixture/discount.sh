#!/bin/bash
# Usage: bash discount.sh PRICE DISCOUNT_PERCENT
printf "%s\n" "$(( $1 * (100 - $2) / 100 ))"
