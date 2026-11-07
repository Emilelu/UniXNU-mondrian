#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CORE=${1:-../UniXNU}
PATCH="$ROOT/patches/unixnu-core/k60-unixnu-core.patch"
git -C "$CORE" apply --check "$PATCH"
git -C "$CORE" apply "$PATCH"
echo "applied $PATCH"
