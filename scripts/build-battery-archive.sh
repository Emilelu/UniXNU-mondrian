#!/bin/bash
# Build the K60 physical battery archive (libK60PhysicalBattery.a) on the host.
#
# Why this exists: scripts/build-k60-physical-battery.py needs a Darwin22
# Kernel.framework SDK, an xcrun shim and a linker that writes BSD archives.
# All three used to be "only on macOS", so the battery class was never linked
# into the kernel and CONFIG_XNU_K60_PHYSICAL_BATTERY stayed inert (P-157).
# Every input is resolved here and named when missing, instead of failing 13
# minutes into a kernel build.
#
# Usage: scripts/build-battery-archive.sh [--out DIR]
set -u

die() { echo "build-battery-archive: FATAL: $*" >&2; exit 1; }

REPO=$(cd "$(dirname "$0")/.." && pwd)
BUILD=${K60_BUILD_TREE:-/opt/k60/trees/k60build}
OUT=${K60_OUT:-$BUILD/out-baseline}
FRAMEWORK=${K60_FRAMEWORK:-/mnt/e/hackios/UniXNU}
MODULE=${K60_BATTERY_MODULE:-/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko}
DEST=${1:-$REPO/build/k60-battery}

board_dir() {
    local found
    found=$(find "$OUT" -maxdepth 4 -name .config -printf '%h\n' 2>/dev/null | head -1)
    [ -n "$found" ] || die "no .config under $OUT; run 'unixnu defconfig' first"
    echo "$found"
}

M=$(board_dir)
TREE=$M/tree
KERNEL_SDK=$TREE/.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A
DTB=$M/device-tree/hardware.dtb

[ -f "$DTB" ] || die "device tree $DTB missing; build the kernel once first"
[ -d "$KERNEL_SDK" ] || die "Kernel.framework SDK missing under $TREE/.cache/fakeroot; build the kernel once first"
[ -f "$MODULE" ] || die "battery module $MODULE missing"
[ -d "$FRAMEWORK/scripts/unixnu" ] || die "framework $FRAMEWORK has no scripts/unixnu"

SHIM_DIR=$BUILD/scripts/linux
[ -x "$SHIM_DIR/xcrun" ] || die "xcrun shim missing at $SHIM_DIR; see P-185"
command -v libtool >/dev/null 2>&1 || die "no libtool on PATH; install scripts/tools/libtool (P-185)"

mkdir -p "$DEST"
PATH=$SHIM_DIR:$BUILD/.toolchain/bin:$PATH \
UNIXNU_SDKROOT=$TREE/.cache/fakeroot \
XNU_TOOLCHAIN_BIN=$BUILD/.toolchain/bin \
python3 "$REPO/scripts/build-k60-physical-battery.py" \
    --tree "$TREE" \
    --output-dir "$DEST" \
    --framework "$FRAMEWORK" \
    --hardware-dtb "$DTB" \
    --battery-module "$MODULE" || die "battery archive build failed"

ARCHIVE=$DEST/libK60PhysicalBattery.a
[ -f "$ARCHIVE" ] || die "builder reported success but $ARCHIVE is missing"
echo "build-battery-archive: $ARCHIVE $(stat -c %s "$ARCHIVE") bytes sha256 $(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
