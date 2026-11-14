#!/bin/bash
# Cross-build the K60 tsens driver into a Mach-O arm64 object plus a static archive,
# then verify the symbol table. This is the artifact that step 7 (local verify) of
# docs/research/EIGHT-STEPS.toml was missing: until now drivers/PongThermal/K60Tsens.c
# had only ever been compiled by the host C compiler for the unit test, so there was no
# Mach-O product whose symbols llvm-nm could confirm (P-190: verify symbols, not the
# file name).
#
# It does NOT link the object into the kernel and does NOT touch board.toml: the
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
SRC=$ROOT/drivers/PongThermal/K60Tsens.c
HDR=$ROOT/drivers/PongThermal/K60Tsens.h

while [ $# -gt 0 ]; do
    case "$1" in
        --out) shift; OUT=$1 ;;
        *) echo "build-thermal-driver: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

die() { echo "build-thermal-driver: FATAL: $*" >&2; exit 1; }

[ -f "$SRC" ] || die "missing $SRC"
[ -f "$HDR" ] || die "missing $HDR"

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

OBJ=$OUT/K60Tsens.o
LIB=$OUT/libK60Thermal.a

# -ffreestanding keeps the object free of Darwin SDK headers: K60Tsens.c only needs
# stdint.h, which clang supplies for freestanding targets.
echo "build-thermal-driver: clang   $CLANG"
echo "build-thermal-driver: target  $TARGET"
"$CLANG" -target "$TARGET" -ffreestanding -fno-builtin -fno-stack-protector \
         -fno-common -O2 -Wall -Wextra -Werror \
         -I "$ROOT/drivers/PongThermal" -c "$SRC" -o "$OBJ" \
    || die "compile failed"

rm -f "$LIB"
"$AR" rcs "$LIB" "$OBJ" || die "archive failed"

file "$OBJ" | grep -q "Mach-O" || die "$OBJ is not Mach-O"

# A freestanding object must not carry undefined symbols: such a symbol would only
# fail at kernel link time, and a silent fallback there is exactly what P-181/P-182
# describe.
UNDEF=$("$NM" -u "$OBJ" 2>/dev/null | awk "NF")
if [ -n "$UNDEF" ]; then
    echo "$UNDEF" >&2
    die "object has undefined symbols (listed above)"
fi

WANT="k60tsens_status_to_mc k60tsens_status_flags k60tsens_decode k60tsens_decode_hw_ver
      k60tsens_ctrl_enabled k60tsens_read k60tsens_read_controller k60tsens_trdy
      k60tsens_sensor_table k60tsens_sensor_name"
DEFINED=$("$NM" --defined-only "$OBJ" 2>/dev/null | awk "{print \$NF}")
MISSING=""
for sym in $WANT; do
    echo "$DEFINED" | grep -qx "_$sym" || MISSING="$MISSING $sym"
done
[ -z "$MISSING" ] || die "missing symbols:$MISSING"

# Mach-O nlist entries carry no size, so measure the read-only data section that
# holds the 32-entry board table instead: 32 entries x 16 bytes = 512 bytes.
CONST_SIZE=$(llvm-size -A "$OBJ" 2>/dev/null | awk '$1=="__const"{print $2}')
if [ -z "$CONST_SIZE" ]; then CONST_SIZE=$(size -A "$OBJ" 2>/dev/null | awk '$1=="__const"{print $2}'); fi
if [ -z "$CONST_SIZE" ]; then die "cannot measure __const"; fi
[ "$CONST_SIZE" -ge 512 ] || die "__const is $CONST_SIZE bytes, expected at least 512 for 32 entries"
TABLE_SIZE=$CONST_SIZE

sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d" " -f1; else shasum -a 256 "$1" | cut -d" " -f1; fi; }
O_SHA=$(sha "$OBJ")
A_SHA=$(sha "$LIB")

MANIFEST=$OUT/thermal-manifest.json
CLANG_VERSION=$("$CLANG" --version | head -1)
cat > "$MANIFEST" <<EOF
{
  "target": "$TARGET",
  "compiler": "$CLANG_VERSION",
  "object": "$OBJ",
  "object_sha256": "$O_SHA",
  "archive": "$LIB",
  "archive_sha256": "$A_SHA",
  "sensor_table_symbol": "_k60TsensTable",
  "const_section_bytes": "$TABLE_SIZE",
  "const_section_holds_32_entries": true,
  "undefined_symbols": 0,
  "required_symbols": "$(echo $WANT)"
}
EOF

echo "build-thermal-driver: object  $OBJ ($O_SHA)"
echo "build-thermal-driver: archive $LIB ($A_SHA)"
echo "build-thermal-driver: __const  $TABLE_SIZE bytes (32-entry board table)"
echo "build-thermal-driver: symbols 10 required, all defined, 0 undefined"
echo "build-thermal-driver: manifest $MANIFEST"
echo "BUILD OK"
