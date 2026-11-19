#!/bin/bash
# Cross-build the K60 thermal sources into Mach-O arm64 objects plus one static archive,
# then verify the symbol tables. This is the artifact that step 7 (local verify) of
# docs/research/EIGHT-STEPS.toml needs: until it existed, drivers/PongThermal/*.c had only
# ever been compiled by the host C compiler for the unit tests, so there was no Mach-O
# product whose symbols llvm-nm could confirm (P-190: verify symbols, not the file name).
#
# Two products:
#   K60Tsens.o         the register reader (drivers/PongThermal/K60Tsens.c)
#   K60ThermalLevel.o  the pressure level arithmetic (drivers/PongThermal/K60ThermalLevel.c)
#
# It does NOT link the objects into the kernel and does NOT touch board.toml: the
# IODeviceMemory mapping and the kernel link line stay with the device step.
#
# Usage:
#   scripts/build-thermal-driver.sh [--out DIR]
#
# Environment:
#   K60_XNU_CLANG  clang to use (default /opt/unixnu-linux/llvm/bin/clang, then clang on PATH)
#   K60_LLVM_AR    archiver (default llvm-ar next to clang, then ar)
#   K60_LLVM_NM    nm (default llvm-nm next to clang, then nm)
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$ROOT/build/thermal
TARGET=arm64-apple-ios16.6.1
INC=$ROOT/drivers/PongThermal

while [ $# -gt 0 ]; do
    case "$1" in
        --out) shift; OUT=$1 ;;
        *) echo "build-thermal-driver: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

die() { echo "build-thermal-driver: FATAL: $*" >&2; exit 1; }

pick() {
    # $1 = env override, $2 = preferred absolute path, $3 = name on PATH
    if [ -n "$1" ] && [ -x "$1" ]; then echo "$1"; return 0; fi
    if [ -x "$2" ]; then echo "$2"; return 0; fi
    command -v "$3" 2>/dev/null && return 0
    return 1
}

CLANG=$(pick "$(printenv K60_XNU_CLANG || true)" /opt/unixnu-linux/llvm/bin/clang clang) || die "no clang"
BINDIR=$(dirname "$CLANG")
AR=$(pick "$(printenv K60_LLVM_AR || true)" "$BINDIR/llvm-ar" llvm-ar) || die "no archiver"
NM=$(pick "$(printenv K60_LLVM_NM || true)" "$BINDIR/llvm-nm" llvm-nm) || die "no nm"

mkdir -p "$OUT" || die "cannot create $OUT"

LIB=$OUT/libK60Thermal.a
rm -f "$LIB"

echo "build-thermal-driver: clang   $CLANG"
echo "build-thermal-driver: target  $TARGET"

# compile SRC OBJ [required symbols...]
#
# -ffreestanding keeps the objects free of Darwin SDK headers: both sources only need
# stdint.h, which clang supplies for freestanding targets.
compile() {
    src=$1; obj=$2; shift 2
    [ -f "$src" ] || die "missing $src"
    "$CLANG" -target "$TARGET" -ffreestanding -fno-builtin -fno-stack-protector \
             -fno-common -O2 -Wall -Wextra -Werror -I "$INC" -c "$src" -o "$obj" \
        || die "compile failed: $src"
    file "$obj" | grep -q "Mach-O" || die "$obj is not Mach-O"

    # A freestanding object must not carry undefined symbols: such a symbol would only
    # fail at kernel link time, and a silent fallback there is exactly what P-181/P-182
    # describe.
    undef=$("$NM" -u "$obj" 2>/dev/null | awk "NF")
    if [ -n "$undef" ]; then
        echo "$undef" >&2
        die "$obj has undefined symbols (listed above)"
    fi

    defined=$("$NM" --defined-only "$obj" 2>/dev/null | awk "{print \$NF}")
    missing=""
    for sym in "$@"; do
        echo "$defined" | grep -qx "_$sym" || missing="$missing $sym"
    done
    [ -z "$missing" ] || die "$obj is missing symbols:$missing"
    echo "build-thermal-driver: symbols $(basename "$obj"): $# required, all defined, 0 undefined"
}

TSENS_OBJ=$OUT/K60Tsens.o
TSENS_WANT="k60tsens_status_to_mc k60tsens_status_flags k60tsens_decode
            k60tsens_decode_hw_ver k60tsens_ctrl_enabled k60tsens_read
            k60tsens_read_controller k60tsens_trdy k60tsens_sensor_table
            k60tsens_sensor_name"
compile "$ROOT/drivers/PongThermal/K60Tsens.c" "$TSENS_OBJ" $TSENS_WANT

LEVEL_OBJ=$OUT/K60ThermalLevel.o
LEVEL_WANT="k60tl_trips k60tl_input_name k60tl_level_name k60tl_input_of_sensor
            k60tl_input_level k60tl_step"
compile "$ROOT/drivers/PongThermal/K60ThermalLevel.c" "$LEVEL_OBJ" $LEVEL_WANT

"$AR" rcs "$LIB" "$TSENS_OBJ" "$LEVEL_OBJ" || die "archive failed"

# Mach-O nlist entries carry no size, so measure the read-only data sections instead.
# The tsens object holds the 32-entry board table: 32 x 16 B = 512 B.
sec_size() {
    # $1 = object, $2 = section name; sums every section of that name
    { llvm-size -A "$1" 2>/dev/null || size -A "$1" 2>/dev/null; } \
        | awk -v want="$2" '$1==want{s+=$2} END{if (s) print s}'
}
TSENS_CONST=$(sec_size "$TSENS_OBJ" __const)
[ -n "$TSENS_CONST" ] || die "cannot measure __const of $TSENS_OBJ"
[ "$TSENS_CONST" -ge 512 ] || die "__const of the tsens object is $TSENS_CONST bytes, expected at least 512 for 32 entries"

# The level object holds four trip tables (4 x 3 x 8 B = 96 B) and the 32-byte sensor map.
LEVEL_CONST=$(sec_size "$LEVEL_OBJ" __const)
[ -n "$LEVEL_CONST" ] || die "cannot measure __const of $LEVEL_OBJ"
[ "$LEVEL_CONST" -ge 128 ] || die "__const of the level object is $LEVEL_CONST bytes, expected at least 128 for the trip tables"

sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d" " -f1; else shasum -a 256 "$1" | cut -d" " -f1; fi; }
O_SHA=$(sha "$TSENS_OBJ")
L_SHA=$(sha "$LEVEL_OBJ")
A_SHA=$(sha "$LIB")

MANIFEST=$OUT/thermal-manifest.json
CLANG_VERSION=$("$CLANG" --version | head -1)
cat > "$MANIFEST" <<EOF
{
  "target": "$TARGET",
  "compiler": "$CLANG_VERSION",
  "object": "$TSENS_OBJ",
  "object_sha256": "$O_SHA",
  "level_object": "$LEVEL_OBJ",
  "level_object_sha256": "$L_SHA",
  "archive": "$LIB",
  "archive_sha256": "$A_SHA",
  "sensor_table_symbol": "_k60TsensTable",
  "const_section_bytes": "$TSENS_CONST",
  "const_section_holds_32_entries": true,
  "level_const_section_bytes": "$LEVEL_CONST",
  "undefined_symbols": 0,
  "required_symbols": "$(echo $TSENS_WANT)",
  "level_required_symbols": "$(echo $LEVEL_WANT)"
}
EOF

echo "build-thermal-driver: object  $TSENS_OBJ ($O_SHA)"
echo "build-thermal-driver: object  $LEVEL_OBJ ($L_SHA)"
echo "build-thermal-driver: archive $LIB ($A_SHA)"
echo "build-thermal-driver: __const  $TSENS_CONST bytes (32-entry board table)"
echo "build-thermal-driver: __const  $LEVEL_CONST bytes (trip tables and sensor map)"
echo "build-thermal-driver: manifest $MANIFEST"
echo "BUILD OK"
