#!/usr/bin/env bash
# Install this repository's OS profiles into a UniXNU checkout.
#
# UniXNU resolves profiles/os/<name> from its own tree, and main does not ship
# an iPhone profile yet. This repository is the source of truth for
# profiles/os/ios-27.0.1-24A446; copy it before defconfig, fetch or build.
#
# usage: scripts/install-os-profile.sh [UNIXNU_DIR]
#        UNIXNU_DIR defaults to board.toml [package] unixnu (relative to here).
set -euo pipefail
DEVICE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UNIXNU=${1:-}
if [ -z "$UNIXNU" ]; then
  UNIXNU=$(python3 - "$DEVICE/board.toml" <<'PY'
import sys, tomllib
package = tomllib.load(open(sys.argv[1], 'rb')).get('package', {})
if 'unixnu' not in package:
    sys.exit('board.toml needs [package] unixnu = "<path of the UniXNU checkout, relative to this repository>"')
print(package['unixnu'])
PY
)
fi
case "$UNIXNU" in /*) ROOT=$UNIXNU ;; *) ROOT=$(cd "$DEVICE/$UNIXNU" && pwd) ;; esac
[ -d "$ROOT/profiles/os" ] || { echo "not a UniXNU checkout: $ROOT" >&2; exit 1; }

shopt -s nullglob
profiles=("$DEVICE"/profiles/os/*/)
[ ${#profiles[@]} -gt 0 ] || { echo "no profiles under $DEVICE/profiles/os" >&2; exit 1; }
for source in "${profiles[@]}"; do
  name=$(basename "$source")
  rm -rf "$ROOT/profiles/os/$name"
  cp -R "$source" "$ROOT/profiles/os/$name"
  echo "installed profiles/os/$name -> $ROOT"
done
