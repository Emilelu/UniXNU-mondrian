#!/bin/bash
# Build libPongWifiNative.a on Linux (no Mac, no Xcode).
#
# Why this exists (2026-11-14): the wifi line could not be built here because
# four separate inputs resolve to macOS-only paths, and each one fails with a
# different message, so every attempt looked like a different bug:
#
#   1. `xcrun` — no Xcode. Use the build tree's shim (scripts/linux/xcrun) and
#      point it at the fakeroot so `-show-sdk-path` returns a real directory.
#   2. `libtool` — absent on Linux. LLVM ships llvm-libtool-darwin, which writes
#      the same BSD archive; /usr/local/bin/libtool is that shim.
#   3. `nw_abi.h` and the Ath12kWifi headers live in the shared UniXNU-sheng
#      checkout, not in this repo (PONG_SHENG_ROOT).
#   4. The ath11k archive and the firmware default to /Volumes/Untitled/... from
#      the author's Mac. Pass --ath11k and PONG_WIFI_FIRMWARE explicitly.
#
# Usage:
#   scripts/build-wifi-archive.sh [--tree DIR] [--out DIR]
#
# The result is build/pong-wifi/libPongWifiNative.a under this checkout, which is
# exactly where scripts/build-xnu-4k-baseline.sh looks when CONFIG_XNU_PONG_WIFI=y
# (XNU_PONG_WIFI_ARCHIVE defaults to $ROOT/build/pong-wifi/libPongWifiNative.a).
set -eu

die() { echo "build-wifi-archive: FATAL: $*" >&2; exit 1; }

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TREE=""
OUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --tree) TREE=${2:?--tree needs a directory}; shift 2 ;;
        --out) OUT=${2:?--out needs a directory}; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

BUILD=${K60_BUILD_TREE:-/opt/k60/trees/k60build}
OUT_TREE=${K60_OUT:-$BUILD/out-baseline}
[ -n "$TREE" ] || TREE=$OUT_TREE/mondrian/ipados-16.6.1-20G81/mondrian/tree
[ -d "$TREE" ] || die "kernel tree $TREE missing; run a kernel build first"
[ -n "$OUT" ] || OUT=$ROOT/build/pong-wifi

SHIM=$BUILD/scripts/linux
[ -x "$SHIM/xcrun" ] || die "$SHIM/xcrun missing (P-185: the build tree lost its shims)"

# libtool does not exist on Linux. Prefer the copy tracked here so a fresh
# checkout works without a system install; fall back to a system one.
LIBTOOL=$ROOT/scripts/tools/libtool
[ -x "$LIBTOOL" ] || LIBTOOL=/usr/local/bin/libtool
[ -x "$LIBTOOL" ] || die "no libtool shim (expected $ROOT/scripts/tools/libtool)"
"$LIBTOOL" -static -o /dev/null >/dev/null 2>&1 || true

SHENG=${PONG_SHENG_ROOT:-/mnt/e/k60-work/impl/wifi/work/src/UniXNU-sheng}
[ -d "$SHENG/drivers/Ath12kWifi/include" ] || die "UniXNU-sheng sources not at $SHENG (set PONG_SHENG_ROOT)"

ATH11K=${PONG_ATH11K_ARCHIVE:-$BUILD/wifi/ath11k/libPongAth11k.a}
[ -f "$ATH11K" ] || die "ath11k archive not at $ATH11K (set PONG_ATH11K_ARCHIVE)"

FW=${PONG_WIFI_FIRMWARE:-/mnt/e/k60-work/firmware/qca6490-wifi}
[ -d "$FW" ] || die "wifi firmware not at $FW (set PONG_WIFI_FIRMWARE)"

export PATH=$ROOT/scripts/tools:/usr/local/bin:$SHIM:$PATH
export UNIXNU_SDKROOT=$TREE/.cache/fakeroot
export XNU_TOOLCHAIN_BIN=${XNU_TOOLCHAIN_BIN:-$BUILD/.toolchain/bin}
export PONG_SHENG_ROOT=$SHENG
export PONG_WIFI_FIRMWARE=$FW

echo "build-wifi-archive: tree=$TREE"
echo "build-wifi-archive: sheng=$SHENG"
echo "build-wifi-archive: ath11k=$ATH11K"
echo "build-wifi-archive: firmware=$FW"
python3 "$ROOT/scripts/build-k60-wifi-native.py" \
    --tree "$TREE" --output-dir "$OUT" --ath11k "$ATH11K"

ARCHIVE=$OUT/libPongWifiNative.a
[ -f "$ARCHIVE" ] || die "the build reported success but $ARCHIVE does not exist"
echo "build-wifi-archive: $ARCHIVE $(stat -c %s "$ARCHIVE") bytes"
echo "build-wifi-archive: sha256 $(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
