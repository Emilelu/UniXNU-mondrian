#!/bin/bash
# Build the K60 thermal IOKit service against a *built* XNU tree and verify that
# every symbol it still needs is exported by that kernel.
#
# Why this script exists: drivers/PongThermal/K60ThermalService.cpp is kernel C++.
# It cannot use the freestanding recipe of scripts/build-thermal-driver.sh (that
# one has no IOKit headers), and it cannot use the unpatched feeds either --
# osfmk/arm64/proc_reg.h ends in "#error processor not supported" unless
# patches/xnu/zzzz-pong-machine.patch has been applied. Both requirements are met
# by a tree already built for this board:
#
#   <tree>/.cache/fakeroot                 real Kernel.framework Headers/PrivateHeaders
#   <tree>/.cache/xnu-work                 patched sources (PONG branch in proc_reg.h)
#   <tree>/build/xnu/ios-obj/EXPORT_HDRS   generated headers, incl. the MIG output
#   <tree>/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp
#                                          the kernel's exported-symbol list
#
# The last one is the point of the exercise: an object whose remaining imports are
# all in all-kpi.exp is linkable into this kernel, while an unknown import would
# only fail at link time (P-181/P-182, P-190: verify symbols, not names).
#
# The three sources are archived together, because K60ThermalService.cpp calls the
# readers in K60Tsens.c and K60ThermalLevel.c; resolving them inside the archive is
# what the kernel link will do.
#
# Usage:
#   scripts/build-thermal-kext.sh [--out DIR] [--tree DIR]
#
# Environment:
#   K60_XNU_TREE      built XNU tree (default /mnt/e/hackios/UniXNU/out/mondrian/tree)
#   K60_XNU_CLANG     C++ compiler (default /opt/unixnu-linux/llvm/bin/clang++)
#   K60_LLVM_AR       archiver (default llvm-ar next to the compiler)
#   K60_LLVM_NM       nm (default llvm-nm next to the compiler)
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$ROOT/build/thermal-kext
TREE=${K60_XNU_TREE:-/mnt/e/hackios/UniXNU/out/mondrian/tree}
TARGET=arm64-apple-ios16.6.1

ALLOW_NO_KPI=0
while [ $# -gt 0 ]; do
    case "$1" in
        --out) shift; OUT=$1 ;;
        --tree) shift; TREE=$1 ;;
        --no-export-list) ALLOW_NO_KPI=1 ;;
        *) echo "build-thermal-kext: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

die() { echo "build-thermal-kext: FATAL: $*" >&2; exit 1; }

FR=$TREE/.cache/fakeroot
EH=$TREE/build/xnu/ios-obj/EXPORT_HDRS
SRC_TREE=$TREE/.cache/xnu-work
KPI=$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp

[ -d "$FR" ] || die "no fakeroot in $TREE (has that tree been built?)"
# EXPORT_HDRS is produced by the xnu make step, which on a cold tree runs AFTER
# the kernel link line is assembled (build-xnu-4k-baseline.sh:1255 vs :896). The
# fakeroot Kernel.framework headers are enough on their own (measured: the same
# sources compile with only fakeroot Headers + PrivateHeaders), so treat
# EXPORT_HDRS as an optimisation, never as a requirement.
if [ ! -d "$EH" ] || [ "${K60_XNU_EXPORT_HDRS:-}" = none ]; then
    echo "build-thermal-kext: WARNING: no EXPORT_HDRS in $TREE; using the fakeroot Kernel.framework headers." >&2
    EH=""
fi
[ -d "$SRC_TREE" ] || die "no .cache/xnu-work in $TREE"
if [ ! -f "$KPI" ]; then
    if [ "$ALLOW_NO_KPI" = 1 ]; then
        echo "build-thermal-kext: WARNING: no all-kpi.exp in $TREE; skipping the import pre-flight." >&2
        echo "build-thermal-kext: WARNING: only do this when the archive is linked into this kernel, because the linker is then the authority." >&2
    else
        die "no all-kpi.exp in $TREE (pass --no-export-list only when the build will link this archive into the kernel)"
    fi
fi

pick() {
    if [ -n "$1" ] && [ -x "$1" ]; then echo "$1"; return 0; fi
    if [ -x "$2" ]; then echo "$2"; return 0; fi
    command -v "$3" 2>/dev/null && return 0
    return 1
}

CXX=$(pick "$(printenv K60_XNU_CLANG || true)" /opt/unixnu-linux/llvm/bin/clang++ clang++) || die "no clang++"
# The two readers are C: compiling them with clang++ would treat them as C++ and
# mangle their names, so the archive would not match the kernel's C symbols.
CC=$(pick "$(printenv K60_XNU_CC || true)" "$(dirname "$CXX")/clang" clang) || die "no clang"
BINDIR=$(dirname "$CXX")
AR=$(pick "$(printenv K60_LLVM_AR || true)" "$BINDIR/llvm-ar" llvm-ar) || die "no archiver"
NM=$(pick "$(printenv K60_LLVM_NM || true)" "$BINDIR/llvm-nm" llvm-nm) || die "no nm"

mkdir -p "$OUT" || die "cannot create $OUT"
LIB=$OUT/libK60ThermalKext.a

echo "build-thermal-kext: tree    $TREE"
echo "build-thermal-kext: clang++ $CXX"
echo "build-thermal-kext: target  $TARGET"

# Flags that matter, each learned the hard way:
#   -nostdinc++        without it clang picks the host's libstdc++ headers
#   no -DXNU_KERNEL_PRIVATE=1
#                      it exposes IOUserClient.h's io_filter_policy_t, a type this
#                      tree never defines, so the compile dies on an unknown type
#   -DKERNEL=1 -DPONG=1 -DARM64_BOARD_CONFIG_PONG=1
#                      KERNEL selects the kernel view of every header; PONG selects
#                      the patched board branch in osfmk/arm64/proc_reg.h
#   no <IOKit/IOMemoryMap.h>
#                      there is no kernel-side header of that name; IOMemoryMap is
#                      forward declared and defined by <IOKit/IOMemoryDescriptor.h>
#   -fno-c++-static-destructors -fno-use-cxa-atexit
#                      the kernel has no C++ runtime, so a static destructor must
#                      not lower to __cxa_atexit/___dso_handle, which the kernel
#                      does not export (measured: without these two the object
#                      imports both)
# EH_INCLUDES is empty on a cold tree; FR_INCLUDES carries the real
# Kernel.framework Headers and PrivateHeaders that installhdrs produced.
EH_INCLUDES=""
if [ -n "$EH" ]; then EH_INCLUDES="-I$EH/iokit -I$EH/osfmk -I$EH/bsd -I$EH/libkern -I$EH/pexpert"; fi
FR_INCLUDES="-I$FR/System/Library/Frameworks/Kernel.framework/Versions/A/PrivateHeaders
             -I$FR/System/Library/Frameworks/Kernel.framework/Versions/A/Headers"
COMMON="-target $TARGET -isysroot $FR
        -ffreestanding -fno-builtin -fno-exceptions -fno-rtti -fno-stack-protector
        -std=gnu++17 -fblocks -O2 -nostdinc++ -Wno-c99-designator -Wno-unused-parameter
        -fno-c++-static-destructors -fno-use-cxa-atexit
        -DKERNEL=1 -DKERNEL_PRIVATE=1 -DPONG=1 -DARM64_BOARD_CONFIG_PONG=1
        $FR_INCLUDES $EH_INCLUDES
        -I$SRC_TREE/iokit -I$SRC_TREE/osfmk -I$SRC_TREE/bsd
        -I$SRC_TREE/libkern -I$SRC_TREE/pexpert -I$SRC_TREE/EXTERNAL_HEADERS
        -I$ROOT/drivers/PongThermal"
# Same include path, C dialect for the two readers.
COMMON_C="-target $TARGET -isysroot $FR
        -ffreestanding -fno-builtin -fno-stack-protector -std=gnu11 -O2
        -Wno-unused-parameter -DKERNEL=1 -DKERNEL_PRIVATE=1
        -DPONG=1 -DARM64_BOARD_CONFIG_PONG=1
        $FR_INCLUDES $EH_INCLUDES
        -I$SRC_TREE/iokit -I$SRC_TREE/osfmk -I$SRC_TREE/bsd
        -I$SRC_TREE/libkern -I$SRC_TREE/pexpert -I$SRC_TREE/EXTERNAL_HEADERS
        -I$ROOT/drivers/PongThermal"

OBJS=""
for src in drivers/PongThermal/K60Tsens.c drivers/PongThermal/K60ThermalLevel.c \
           drivers/PongThermal/K60ThermalService.cpp; do
    [ -f "$ROOT/$src" ] || die "missing $src"
    obj=$OUT/$(basename "${src%.*}").o
    case "$src" in
        *.cpp) compiler=$CXX; flags=$COMMON ;;
        *)     compiler=$CC;  flags=$COMMON_C ;;
    esac
    # shellcheck disable=SC2086
    "$compiler" $flags -c "$ROOT/$src" -o "$obj" || die "compile failed: $src"
    file "$obj" | grep -q "Mach-O" || die "$obj is not Mach-O"
    OBJS="$OBJS $obj"
done

# ld64 rejects a GNU '//' long-name table and silently drops the whole archive,
# so the Darwin format is mandatory (P-181/P-182).
rm -f "$LIB"
# shellcheck disable=SC2086
"$AR" --format=darwin rcs "$LIB" $OBJS || die "archive failed"
file "$LIB" | grep -q "current ar archive" || die "$LIB is not a Darwin archive"

# --- what the object model must define --------------------------------------
DEFINED=$("$NM" --defined-only "$LIB" 2>/dev/null | awk 'NF{print $NF}' | sort -u)
[ -n "$DEFINED" ] || die "cannot read symbols from $LIB"
# llvm-nm prints Mach-O names with their leading underscore, and C++ names start
# with __Z, so every entry is matched with and without one extra underscore.
WANT="_k60_thermal_start _ZN16K60ThermalSensor5startEP9IOService
      _ZN16K60ThermalSensor13sampleDomainsEPi _ZN16K60ThermalSensor18setPhysicalWindowsEyy
      _ZN24AppleSMCSensorDispatcher7publishEP16K60ThermalSensorS1_
      _ZN34AppleSMCSensorDispatcherUserClient14externalMethodEjP25IOExternalMethodArgumentsP24IOExternalMethodDispatchP8OSObjectPv
      _ZN34AppleSMCSensorDispatcherUserClient12initWithTaskEP4taskPvj
      _k60tsens_read_controller _k60tl_step _k60tl_input_of_sensor"
missing=""
for sym in $WANT; do
    echo "$DEFINED" | grep -qxF "$sym" || echo "$DEFINED" | grep -qxF "_$sym" || missing="$missing $sym"
done
[ -z "$missing" ] || die "archive is missing symbols:$missing"
echo "build-thermal-kext: defined $(echo "$DEFINED" | wc -l) symbols, all $(echo $WANT | wc -w) required ones present"

# --- what is still imported must come from the kernel -----------------------
UNDEF=$("$NM" -u "$LIB" 2>/dev/null | awk 'NF{print $NF}' | sort -u)
# all-kpi.exp is a linker -exported_symbols_list: one symbol per line, some lines
# indented, with '#' comments. Normalise it once, then compare fixed strings.
IMPORTED=0
ALL_EXPORTED=unchecked
if [ -f "$KPI" ]; then
    EXPORTS=$OUT/kernel-exports.txt
    sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$KPI" | grep -v '^#' | grep -v '^$' | sort -u > "$EXPORTS"
    UNRESOLVED=""
    for sym in $UNDEF; do
        if echo "$DEFINED" | grep -qxF "$sym"; then continue; fi
        IMPORTED=$((IMPORTED + 1))
        grep -qxF -- "$sym" "$EXPORTS" || UNRESOLVED="$UNRESOLVED $sym"
    done
    [ -z "$UNRESOLVED" ] || die "symbols the kernel does not export:$UNRESOLVED"
    ALL_EXPORTED=true
    echo "build-thermal-kext: $IMPORTED kernel imports, all exported by the kernel"
else
    for sym in $UNDEF; do
        if echo "$DEFINED" | grep -qxF "$sym"; then continue; fi
        IMPORTED=$((IMPORTED + 1))
    done
    echo "build-thermal-kext: $IMPORTED kernel imports, export list not available (pre-flight skipped)" >&2
fi

sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d" " -f1; else shasum -a 256 "$1" | cut -d" " -f1; fi; }
A_SHA=$(sha "$LIB")
CLANG_VERSION=$("$CXX" --version | head -1)

MANIFEST=$OUT/thermal-kext-manifest.json
cat > "$MANIFEST" <<EOF
{
  "target": "$TARGET",
  "compiler": "$CLANG_VERSION",
  "xnu_tree": "$TREE",
  "sources": ["drivers/PongThermal/K60Tsens.c", "drivers/PongThermal/K60ThermalLevel.c", "drivers/PongThermal/K60ThermalService.cpp"],
  "archive": "$LIB",
  "archive_sha256": "$A_SHA",
  "info_plist": "$ROOT/drivers/PongThermal/Info.plist",
  "required_symbols": "$(echo $WANT)",
  "defined_symbols": $(echo "$DEFINED" | wc -l),
  "kernel_imports": $IMPORTED,
  "kernel_imports_all_exported": "$ALL_EXPORTED",
  "kernel_export_list": "$KPI"
}
EOF

echo "build-thermal-kext: archive $LIB ($A_SHA)"
echo "build-thermal-kext: manifest $MANIFEST"
echo "build-thermal-kext: BUILD OK"
