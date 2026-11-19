#!/bin/sh
# Print the XNU builder the board's OS profile needs.
#
#   sh scripts/pick-xnu-builder.sh [board.toml]
#
# 16.6.1 line -> this repository's Pong builder (MACHINE_CONFIGS=PONG, the K60
# archives, the Metal blob). Every other profile -> the generic UniXNU builder,
# which builds the arm64e 4 KiB slice the iOS 27 stage-0 needs.
set -eu
board=${1:-board.toml}
profile=$(python3 - "$board" <<'PY'
import sys, tomllib
try:
    data = tomllib.load(open(sys.argv[1], 'rb'))
except (FileNotFoundError, OSError):
    print('')
else:
    print(data.get('board', {}).get('os_profile', ''))
PY
)
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$profile" in
  ipados-16.6.1-20G81) echo "$here/build-xnu-4k-baseline.sh" ;;
  *)                   echo "$here/build-xnu-generic.sh" ;;
esac
