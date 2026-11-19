#!/bin/bash
# Prove that the kernel link line in docs/research/thermal/07-INTEGRATION.md §3 works:
# -Wl,-force_load,<libK60ThermalKext.a> must pull the archive members in and resolve
# the k60_thermal_start() reference, without introducing any import the kernel does
# not export.
#
# Why a synthetic caller instead of drivers/ArmDTPlatform/ArmDTPlatform.cpp: the real
# hook lives in a file outside the thermal line's write scope (task-3), so this script
# compiles a five-line caller that declares the same extern "C" symbol and calls it.
# The linker cannot tell the difference -- that is exactly what -force_load is for.
#
# What it checks:
#   1. partial link (ld -r) of the caller + -force_load archive succeeds
#   2. _k60_thermal_start is no longer undefined in the merged object
#   3. the same link WITHOUT -force_load still leaves it undefined (the control:
#      proves the flag is load-bearing, not decorative)
#   4. every symbol the archive imports is either defined inside the archive or
#      present in the kernel's all-kpi.exp export list
#
# Usage: scripts/build-thermal-link-check.sh [--tree DIR] [--out DIR]
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$ROOT/build/thermal-link-check
TREE=${K60_XNU_TREE:-/mnt/e/hackios/UniXNU/out/mondrian/tree}

while [ $# -gt 0 ]; do
    case "$1" in
        --out) shift; OUT=$1 ;;
        --tree) shift; TREE=$1 ;;
        *) echo "build-thermal-link-check: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

die() { echo "build-thermal-link-check: FATAL: $*" >&2; exit 1; }

LIB=$ROOT/build/thermal-kext/libK60ThermalKext.a
[ -f "$LIB" ] || die "no $LIB (run scripts/build-thermal-kext.sh first)"

FR=$TREE/.cache/fakeroot
EH=$TREE/build/xnu/ios-obj/EXPORT_HDRS
SRCT=$TREE/.cache/xnu-work
KPI=$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp
[ -d "$FR" ] || die "no fakeroot in $TREE"
[ -f "$KPI" ] || die "no all-kpi.exp in $TREE"

CXX=${K60_XNU_CLANG:-/opt/unixnu-linux/llvm/bin/clang++}
[ -x "$CXX" ] || CXX=clang++
LD=${K60_LD64:-/opt/unixnu-linux/CommandLineTools/usr/bin/ld}
[ -x "$LD" ] || LD=ld
NM=${K60_LLVM_NM:-/usr/bin/llvm-nm}
[ -x "$NM" ] || NM=llvm-nm

mkdir -p "$OUT" || die "cannot create $OUT"
TARGET=arm64-apple-ios16.6.1

cat > "$OUT/caller.cpp" <<'EOF'
// Stand-in for the ArmDTPlatform hook in docs/research/thermal/07-INTEGRATION.md §4.
extern "C" int k60_thermal_start(void);
extern "C" int k60_thermal_link_probe(void);
extern "C" int k60_thermal_link_probe(void) { return k60_thermal_start(); }
EOF

echo "build-thermal-link-check: tree  $TREE"
echo "build-thermal-link-check: ld    $LD"

# shellcheck disable=SC2086
"$CXX" -target $TARGET -isysroot "$FR" \
    -ffreestanding -fno-builtin -fno-exceptions -fno-rtti -fno-stack-protector \
    -std=gnu++17 -fblocks -O2 -nostdinc++ -Wno-c99-designator -Wno-unused-parameter \
    -fno-c++-static-destructors -fno-use-cxa-atexit \
    -DKERNEL=1 -DKERNEL_PRIVATE=1 -DPONG=1 -DARM64_BOARD_CONFIG_PONG=1 \
    -I"$EH/iokit" -I"$EH/osfmk" -I"$EH/bsd" -I"$EH/libkern" -I"$EH/pexpert" \
    -I"$SRCT/iokit" -I"$SRCT/osfmk" -I"$SRCT/bsd" -I"$SRCT/libkern" -I"$SRCT/pexpert" \
    -I"$SRCT/EXTERNAL_HEADERS" \
    -c "$OUT/caller.cpp" -o "$OUT/caller.o" || die "caller did not compile"

link() {
    "$LD" -r -arch arm64 -platform_version ios 16.0 16.6.1 -o "$1" "$OUT/caller.o" "${@:2}" \
        2> "$OUT/$(basename "${1%.o}").ld.log"
}

# Control first: without the flag the reference must survive the link.
link "$OUT/merged-no-force.o" || die "control link failed (see $OUT/merged-no-force.ld.log)"
NO_FORCE=$("$NM" -u "$OUT/merged-no-force.o" 2>/dev/null | grep -c '^_k60_thermal_start$' || true)
[ "$NO_FORCE" = 1 ] || die "control link unexpectedly resolved k60_thermal_start without -force_load"
echo "build-thermal-link-check: control OK (k60_thermal_start still undefined without the flag)"

link "$OUT/merged-force.o" -force_load "$LIB" || die "force_load link failed (see $OUT/merged-force.ld.log)"
LEFT=$("$NM" -u "$OUT/merged-force.o" 2>/dev/null | grep -c '^_k60_thermal_start$' || true)
[ "$LEFT" = 0 ] || die "-force_load did not resolve k60_thermal_start"
echo "build-thermal-link-check: -force_load resolved k60_thermal_start"

# Every import of the archive must come from the archive itself or from the kernel.
sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$KPI" | grep -v '^#' | grep -v '^$' | sort -u > "$OUT/kernel-exports.txt"
"$NM" --defined-only "$LIB" 2>/dev/null | awk 'NF && $0 !~ /:$/ {print $NF}' | sort -u > "$OUT/archive-defined.txt"
"$NM" -u "$LIB" 2>/dev/null | awk 'NF && $0 !~ /:$/ {print $NF}' | sort -u > "$OUT/archive-imports.txt"
comm -23 "$OUT/archive-imports.txt" "$OUT/archive-defined.txt" > "$OUT/archive-external.txt"
comm -23 "$OUT/archive-external.txt" "$OUT/kernel-exports.txt" > "$OUT/archive-unresolved.txt"
UNRESOLVED=$(wc -l < "$OUT/archive-unresolved.txt")
[ "$UNRESOLVED" = 0 ] || { cat "$OUT/archive-unresolved.txt" >&2; die "$UNRESOLVED archive imports are not in all-kpi.exp"; }
echo "build-thermal-link-check: $(wc -l < "$OUT/archive-external.txt") archive imports, all in all-kpi.exp"

sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d" " -f1; else shasum -a 256 "$1" | cut -d" " -f1; fi; }
cat > "$OUT/link-check.json" <<EOF
{
  "archive": "$LIB",
  "archive_sha256": "$(sha "$LIB")",
  "merged_object": "$OUT/merged-force.o",
  "merged_sha256": "$(sha "$OUT/merged-force.o")",
  "force_load_resolved_entry_point": true,
  "control_without_force_load_leaves_undefined": true,
  "archive_external_imports": $(wc -l < "$OUT/archive-external.txt"),
  "archive_unresolved_imports": 0,
  "kernel_export_list": "$KPI"
}
EOF
echo "build-thermal-link-check: report $OUT/link-check.json"
echo "build-thermal-link-check: LINK OK"
