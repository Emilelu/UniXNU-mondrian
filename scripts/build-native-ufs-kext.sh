#!/bin/bash
# Link the NativeUfs objects into a kext bundle, so route B can carry the driver
# as its own fileset entry instead of force-loading it into com.apple.kernel.
#
# Why a bundle and not an archive: on 27 the eleven IOBlockStorageDevice symbols
# live in the sibling fileset entry com.apple.iokit.IOStorageFamily, so a
# force-loaded archive has nothing to bind them against (26 undefined symbols,
# measured on the 16.6.1 line as 14 -> 26 in docs/research/storage/UFS27-GATE.md).
# A kext bundle is resolved by IOKit at prelink time against that sibling entry,
# which is exactly the shape Apple ships.
#
# The link is `ld -kext`, never a hand-written `__kmod_info` section: the C++
# layout of kmod_info has to match the running kernel field for field, and a
# wrong field is read as garbage with no diagnostic. `-kext` makes the linker
# emit MH_KEXT_BUNDLE and the kmod_info the kernel expects.
#
# Nothing here has been run on this host: the lane forbids builds, there are no
# objects, and no Darwin linker is installed. `--dry-run` prints the command that
# would run; that is the supported mode until a build exists. The bundle is then
# graded by scripts/check-ufs27-storage-entry.py (entry / kmod / exports) and
# scripts/check-ios27-storage-entries.py --require-entry.
#
# Usage:
#   scripts/build-native-ufs-kext.sh --dry-run
#   scripts/build-native-ufs-kext.sh [--objects DIR] [--out DIR] [--ld PATH]
#                                    [--platform ios] [--sdk 27.0] [--min 27.0]
#
# Environment:
#   K60_LD             linker (default ld from PATH; must accept -kext)
#   K60_UFS_OBJECTS    directory holding NativeUfs.o/PongUfsTransport.o/verified_root.o
#                      (default $ROOT/build/native-ufs/objects, written by
#                      scripts/build-native-ufs-linux.py --out build/native-ufs)
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OBJECTS=${K60_UFS_OBJECTS:-$ROOT/build/native-ufs/objects}
OUT=$ROOT/build/native-ufs/NativeUfs.kext
LD_BIN=${K60_LD:-ld}
PLATFORM=ios
SDK=27.0
MIN=27.0
DRY_RUN=0
PLIST=$ROOT/drivers/NativeUfs/Info.plist
MEMBERS=(NativeUfs.o PongUfsTransport.o verified_root.o)

while [ $# -gt 0 ]; do
    case "$1" in
        --objects) shift; OBJECTS=$1 ;;
        --out) shift; OUT=$1 ;;
        --ld) shift; LD_BIN=$1 ;;
        --platform) shift; PLATFORM=$1 ;;
        --sdk) shift; SDK=$1 ;;
        --min) shift; MIN=$1 ;;
        --dry-run) DRY_RUN=1 ;;
        *) echo "build-native-ufs-kext: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

die() { echo "build-native-ufs-kext: FATAL: $*" >&2; exit 1; }
say() { echo "build-native-ufs-kext: $*"; }

BUNDLE=$OUT/Contents/MacOS/NativeUfs
ARGS=(-arch arm64e -kext -platform_version "$PLATFORM" "$MIN" "$SDK"
      -undefined dynamic_lookup -o "$BUNDLE")

missing=0
for member in "${MEMBERS[@]}"; do
    if [ -f "$OBJECTS/$member" ]; then
        ARGS+=("$OBJECTS/$member")
    else
        say "missing object $OBJECTS/$member"
        ARGS+=("$OBJECTS/$member")
        missing=$((missing + 1))
    fi
done

say "objects $OBJECTS"
say "output  $OUT"
say "linker  $LD_BIN"
say "member  arm64e, MH_KEXT_BUNDLE (ld -kext)"

if [ "$DRY_RUN" = 1 ]; then
    printf 'build-native-ufs-kext: %s %s\n' "$LD_BIN" "${ARGS[*]}"
    say "dry run: nothing was written"
    [ "$missing" -gt 0 ] && say "$missing object(s) would still have to be compiled by scripts/build-native-ufs-linux.py"
    exit 0
fi

[ "$missing" -eq 0 ] || die "$missing object(s) missing under $OBJECTS; run scripts/build-native-ufs-linux.py --out build/native-ufs first"
command -v "$LD_BIN" >/dev/null 2>&1 || die "no $LD_BIN on PATH; a Darwin linker is required for -kext"
[ -f "$PLIST" ] || die "no $PLIST to copy into the bundle"

mkdir -p "$OUT/Contents/MacOS" || die "cannot create $OUT"
say "link $(basename "$BUNDLE")"
"$LD_BIN" "${ARGS[@]}" || die "the link failed; do not hand-write __kmod_info as a workaround"
cp "$PLIST" "$OUT/Contents/Info.plist" || die "cannot copy $PLIST"
say "bundle $OUT"
say "next    python3 scripts/check-ufs27-storage-entry.py --kernelcache <collection>"
say "BUILD OK"
