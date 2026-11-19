#!/bin/bash
# Offline only: no device access, no MMIO, no physical memory.
#
# The GLINK intent list lives in drivers/PongPower but is not one of the six
# pure policy modules the power page's portability preflight covers, so it gets
# its own runner.  D9 (2026-11-19): this tree drops a zero-size intent entry and
# keeps the rest, while the cellular line's 0622 patch rejects the whole list;
# the lead accepted the divergence and asked for this test.
#
# usage: run-k60-glink-host.sh [OUTPUT_DIR]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-}
if [ -n "$OUT" ]; then mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd); else OUT=$(mktemp -d); fi
cd "$REPO"
CFLAGS=(-std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongPower)
cc "${CFLAGS[@]}" scripts/tests/test-k60-glink-intent.c \
  drivers/PongPower/QcomGlink.c -o "$OUT/glink-intent"
out=$("$OUT/glink-intent")
printf '%s\n' "$out"
if ! printf '%s\n' "$out" | grep -q "TESTS OK "; then
  echo "glink-host: the intent suite did not pass" >&2
  exit 1
fi
echo "glink-host: OK (binaries in $OUT)"
