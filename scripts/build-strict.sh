#!/bin/bash
# Strict K60 build: one command, one manifest, no silent fallbacks.
#
# Why this exists (P-181/P-182): every "successful" build between 2026-11-13
# 16:43 and 17:37 repackaged a stale kernel.macho, because the wrapper matched
# the line "== kernel: bootstrap pass for the compile records" and then accepted
# any existing file. Two boots were judged on artifacts that never changed.
#
# Usage:
#   scripts/build-strict.sh <tag> --fd <file.fd> [--kernel-arg NAME=VALUE ...]
#
# Guarantees:
#   * passes the real exit code of every stage (no pipe into grep)
#   * refuses to run with UNIXNU_SKIP_GATES set, and never sets it
#   * requires --fd; the firmware volume is archived with its sha256
#   * requires kernel.macho to be newer than this run's marker
#   * writes <out>/build-manifest.json with every component sha256
set -u

die() { echo "build-strict: FATAL: $*" >&2; exit 1; }

TAG=${1:?usage: build-strict.sh <tag> --fd <file.fd> [--kernel-arg K=V ...]}
shift
FD=""
KARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --fd) FD=${2:?--fd needs a file}; shift 2 ;;
        --kernel-arg) KARGS+=("${2:?--kernel-arg needs NAME=VALUE}"); shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done
[ -z "${UNIXNU_SKIP_GATES:-}" ] || die "UNIXNU_SKIP_GATES is set; strict builds run every gate"
[ -n "$FD" ] || die "--fd is required; a build must name the firmware volume it packs"
[ -f "$FD" ] || die "--fd $FD does not exist"

REPO=$(cd "$(dirname "$0")/.." && pwd)
DEV=${K60_DEVICE_INPUT:-/opt/k60/trees/usb-cdc-mainline/device}
BUILD=${K60_BUILD_TREE:-/opt/k60/trees/k60build}
OUT=${K60_OUT:-$BUILD/out-baseline}
ART=${K60_ARTIFACTS:-/mnt/e/k60-work/artifacts}
RUN=$ART/$TAG
LOGS=$RUN/logs
MARK=$RUN/.build-marker
export HOME=${HOME:-/root}
export K60_REPO=$REPO

mkdir -p "$LOGS" "$ART/fd" || die "cannot create $RUN"
[ -d "$DEV" ] || die "device input $DEV missing"
[ -d "$BUILD" ] || die "build tree $BUILD missing"

M=$OUT/mondrian/ipados-16.6.1-20G81/mondrian
KERNEL=$M/kernel/kernel.macho

# --- frozen inputs -----------------------------------------------------------
# Every file that can change the kernel is hashed before the build; a later
# boot is only comparable if the same list hashes the same.
freeze() {
    ( cd "$REPO" && find board.toml dts patches/xnu scripts -type f -print0 \
        | sort -z | xargs -0 sha256sum )
}
freeze > "$RUN/frozen-before.txt" || die "cannot hash the frozen inputs"
FROZEN_SHA=$(sha256sum "$RUN/frozen-before.txt" | cut -d' ' -f1)
SERIES_SHA=$(sha256sum "$REPO/patches/xnu/series" | cut -d' ' -f1)
SERIES_COUNT=$(grep -c . "$REPO/patches/xnu/series")

echo "build-strict: tag=$TAG series=$SERIES_COUNT frozen=$FROZEN_SHA"

# --- kernel ------------------------------------------------------------------
touch "$MARK"; sleep 2
if ! "$BUILD/unixnu" build kernel -D "$DEV" --out "$OUT" > "$LOGS/kernel.log" 2>&1; then
    tail -30 "$LOGS/kernel.log" >&2
    die "kernel build failed (see $LOGS/kernel.log)"
fi
[ -s "$KERNEL" ] || die "kernel.macho missing after a successful build"
[ "$KERNEL" -nt "$MARK" ] || die "kernel.macho is older than this build: stale artifact"
KERNEL_SHA=$(sha256sum "$KERNEL" | cut -d' ' -f1)
echo "build-strict: kernel $KERNEL_SHA $(stat -c %s "$KERNEL") bytes"

# --- payload -----------------------------------------------------------------
if ! "$BUILD/unixnu" build payload -D "$DEV" --out "$OUT" --kernel "$KERNEL" \
        > "$LOGS/payload.log" 2>&1; then
    tail -30 "$LOGS/payload.log" >&2
    die "payload build failed (see $LOGS/payload.log)"
fi
PAYLOAD=$M/payload/payload.img
ADT=$M/payload/kernel.macho.adt
[ -s "$PAYLOAD" ] || die "payload.img missing"
PAYLOAD_SHA=$(sha256sum "$PAYLOAD" | cut -d' ' -f1)

# --- boot image --------------------------------------------------------------
FD_ARCH=$ART/fd/$TAG-$(sha256sum "$FD" | cut -c1-12).fd
cp -f "$FD" "$FD_ARCH" || die "cannot archive the firmware volume"
FD_SHA=$(sha256sum "$FD_ARCH" | cut -d' ' -f1)

BOOTIMG=("$BUILD/unixnu" bootimg -D "$DEV" --out "$OUT"
         --uefi /mnt/e/hackios/uefi-mondrian
         --edk2 /mnt/e/hackios/uefi-mondrian/Mu_Basecore
         --dtb "$M/device-tree/hardware.dtb"
         --fd "$FD_ARCH" -o "$RUN/boot.img")
for kv in "${KARGS[@]:-}"; do
    [ -n "$kv" ] || continue
    BOOTIMG+=(--kernel-arg "$kv")
done
if ! "${BOOTIMG[@]}" > "$LOGS/bootimg.log" 2>&1; then
    tail -30 "$LOGS/bootimg.log" >&2
    die "bootimg failed (see $LOGS/bootimg.log)"
fi
[ -s "$RUN/boot.img" ] || die "boot.img missing"
BOOT_SHA=$(sha256sum "$RUN/boot.img" | cut -d' ' -f1)

freeze > "$RUN/frozen-after.txt" || die "cannot re-hash the frozen inputs"
if ! cmp -s "$RUN/frozen-before.txt" "$RUN/frozen-after.txt"; then
    diff -u "$RUN/frozen-before.txt" "$RUN/frozen-after.txt" >&2 || true
    die "frozen inputs changed during the build; this run is void"
fi

# --- manifest ----------------------------------------------------------------
sha_or_empty() { [ -f "$1" ] && sha256sum "$1" | cut -d' ' -f1 || echo ""; }
DTB=$M/device-tree/hardware.dtb
GIT_BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
GIT_HEAD=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)
GIT_DIRTY=$(git -C "$REPO" status --porcelain 2>/dev/null | wc -l)

python3 - "$RUN/build-manifest.json" <<PY || die "cannot write the manifest"
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
m = {
    "tag": "$TAG",
    "built_at": "$(date -Iseconds)",
    "repo": {"branch": "$GIT_BRANCH", "head": "$GIT_HEAD", "dirty_files": $GIT_DIRTY},
    "series": {"count": $SERIES_COUNT, "sha256": "$SERIES_SHA"},
    "frozen": {"list_sha256": "$FROZEN_SHA", "file": "frozen-before.txt"},
    "components": {
        "kernel_built": "$KERNEL_SHA",
        "payload": "$PAYLOAD_SHA",
        "payload_kernel": None,
        "adt": "$(sha_or_empty "$ADT")",
        "dtb": "$(sha_or_empty "$DTB")",
        "fd": "$FD_SHA",
        "fd_path": "$FD_ARCH",
        "boot_img": "$BOOT_SHA",
        "boot_img_path": "$RUN/boot.img",
    },
    "kernel_args": [$(printf '"%s",' "${KARGS[@]:-}" | sed 's/,$//')],
    "logs": "$LOGS",
}
out.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
print("build-strict: manifest", out)
PY

echo "build-strict: boot.img $BOOT_SHA"
echo "build-strict: verify with scripts/verify-boot-image.py --manifest $RUN/build-manifest.json"
