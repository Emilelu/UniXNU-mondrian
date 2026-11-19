#!/usr/bin/env bash
# Build the iOS 27 (24A446) kernel with the Wi-Fi station archive linked in, then
# prove the driver is actually in the linked kernel.
#
# The 27 line runs the framework's generic builder (board.toml [board] os_profile is
# not the 16.6.1 line), so the archive only enters the link through
# XNU_PONG_WIFI=1 + XNU_PONG_WIFI_ARCHIVE, which scripts/build-xnu-generic.sh reads.
# A successful link is not evidence - -force_load over an archive whose objects were
# compiled out also links - so the last step counts defined PongWifi symbols and
# fails when there are none (scripts/check-wifi-symbols.py).
#
# Usage: scripts/build-wifi27-kernel.sh [--framework DIR] [--device DIR]
#                                      [--archive FILE] [--os PROFILE] [--skip-gates]
#   --framework  UniXNU build driver checkout (default $UNIXNU_REPO or ../UniXNU)
#   --device     device repository (default: the checkout this script lives in)
#   --archive    libPongWifiNative.a (default $XNU_PONG_WIFI_ARCHIVE or
#                build/pong-wifi/libPongWifiNative.a)
#   --os         OS profile (default ios-27.0.1-24A446; the ipados- key applies the
#                16 series and fails at osfmk/arm64/start.s:33)
#   --skip-gates pass --skip-gates to the driver (needed while check-rules.py still
#                reports its pitfall-heading defect on this framework)
#
# Environment: K60_DEVICE_INPUT is exported for the gates; WIFI27_MACH lets you
# check an already built kernel without rebuilding.
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
FRAMEWORK=${UNIXNU_REPO:-$REPO/../UniXNU}
DEVICE=$REPO
OS_PROFILE=ios-27.0.1-24A446
ARCHIVE=${XNU_PONG_WIFI_ARCHIVE:-$REPO/build/pong-wifi/libPongWifiNative.a}
SKIP_GATES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --framework) FRAMEWORK=$2; shift 2 ;;
    --device) DEVICE=$2; shift 2 ;;
    --archive) ARCHIVE=$2; shift 2 ;;
    --os) OS_PROFILE=$2; shift 2 ;;
    --skip-gates) SKIP_GATES=1; shift ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "build-wifi27-kernel: unknown argument $1" >&2; exit 2 ;;
  esac
done

test -f "$FRAMEWORK/unixnu" || { echo "build-wifi27-kernel: no build driver at $FRAMEWORK" >&2; exit 2; }
test -f "$ARCHIVE" || { echo "build-wifi27-kernel: no station archive at $ARCHIVE" >&2; exit 2; }
export XNU_PONG_WIFI=1
export XNU_PONG_WIFI_ARCHIVE=$ARCHIVE
export K60_DEVICE_INPUT=${K60_DEVICE_INPUT:-$FRAMEWORK/out/device-input}

if [ -z "${WIFI27_MACH:-}" ]; then
  set -- build kernel --device "$DEVICE" --os "$OS_PROFILE"
  [ "$SKIP_GATES" = 1 ] && set -- "$@" --skip-gates
  echo "build-wifi27-kernel: archive $ARCHIVE"
  ( cd "$FRAMEWORK" && python3 unixnu "$@" )
fi

# Find the linked kernel: the 27 line's object tree is DEVELOPMENT_ARM64_BCM2837, and
# the prelink input is the unstripped nocTF Mach-O next to it.
BOARD=$(python3 - "$DEVICE/board.toml" <<'PY'
import sys, tomllib
board = tomllib.load(open(sys.argv[1], 'rb'))
print(board.get('board', {}).get('name', 'mondrian'))
PY
)
OUT_ROOT=$FRAMEWORK/out/$BOARD/$OS_PROFILE
MACH=${WIFI27_MACH:-$(find "$OUT_ROOT" -maxdepth 8 -name 'mach.development.*.unstripped.noctf' -newer "$ARCHIVE" 2>/dev/null | head -1)}
if [ -z "$MACH" ]; then
  MACH=$(find "$OUT_ROOT" -maxdepth 8 -name 'mach.development.*.unstripped.noctf' 2>/dev/null | head -1)
fi
test -n "$MACH" || { echo "build-wifi27-kernel: no linked kernel under $OUT_ROOT" >&2; exit 3; }
echo "build-wifi27-kernel: linked kernel $MACH"
exec python3 "$REPO/scripts/check-wifi-symbols.py" "$MACH"