#!/usr/bin/env bash
# Self-test for `kc-surface.py adt`. No build, no device, no network.
#
# The check has to prove five things, or it is not a criterion:
#   1. it passes on a tree that does declare the controller;
#   2. a usb node WITHOUT unixnu,adt-name is not enough (devicetree.py generate()
#      only exports marked nodes) -- the plain-node case must fail;
#   3. a board [adt.arm-io] block alone IS enough (that path skips the dts);
#   4. a name declared on both sides is refused (generate() raises on it);
#   5. the 27 tree as built declares nothing, so it must fail.
#
# Needs dtc and python3 with tomllib (both present in the WSL distribution).
# Run from the repository root:  bash scripts/usb27/test-adt-check.sh
set -u

here=$(cd "$(dirname "$0")" && pwd)
check="$here/kc-surface.py"
fixture_dts="$here/fixtures/adt-usb.dts"
fixture_board="$here/fixtures/board-adt-usb.toml"
dtb27=${USB27_DTB:-/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/device-tree/hardware.dtb}
board27=${USB27_BOARD:-/mnt/e/hackios/k60-gates/board.toml}
failures=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

report() {  # report NAME EXPECTED_EXIT ACTUAL_EXIT OUTPUT
    if [ "$2" = "$3" ]; then
        echo "PASS $1 (exit $3)"
    else
        echo "FAIL $1 (expected exit $2, got $3)"
        echo "$4" | sed 's/^/     /'
        failures=$((failures + 1))
    fi
}

compile() {  # compile NAME DTS
    dtc -I dts -O dtb -o "$tmp/$1.dtb" "$2" 2>"$tmp/$1.log"
    if [ ! -s "$tmp/$1.dtb" ]; then
        echo "FAIL $1 did not compile"
        sed 's/^/     /' "$tmp/$1.log"
        echo "RESULT FAIL (1)"
        exit 1
    fi
}

compile full "$fixture_dts"
# 2/3/4: derived sources, so the numbers live in one file only.
sed 's/^[[:space:]]*unixnu,adt-name = "usb0";$//' "$fixture_dts" >"$tmp/no-name.dts"
compile no-name "$tmp/no-name.dts"
sed 's/unixnu,adt-name = "usb0"/unixnu,adt-name = "pong-usb"/' "$fixture_dts" >"$tmp/dup.dts"
compile dup "$tmp/dup.dts"

# 1. exported node + board block: the check must return 0
out=$(python3 "$check" adt "$tmp/full.dtb" "$fixture_board" --expect-base 0xa600000 2>&1)
report "fixture exports arm-io/usb0 and declares 0xa600000" 0 $? "$out"

# 2. unmarked node against a board without a usb block: must fail
out=$(python3 "$check" adt "$tmp/no-name.dtb" "$board27" 2>&1)
report "usb node without unixnu,adt-name reaches no ADT child" 1 $? "$out"

# 3. the board half alone is a declaration: must pass
out=$(python3 "$check" adt "$tmp/no-name.dtb" "$fixture_board" 2>&1)
report "board [adt.arm-io] block alone declares the controller" 0 $? "$out"

# 4. the same name on both sides is a generate() error: must fail
out=$(python3 "$check" adt "$tmp/dup.dtb" "$fixture_board" 2>&1)
report "duplicate arm-io name is refused" 1 $? "$out"

# 5. a base neither side declares must fail, so the window matters
out=$(python3 "$check" adt "$tmp/full.dtb" "$fixture_board" --expect-base 0x88e8000 2>&1)
report "expected base 0x88e8000 (QMP) is not declared anywhere" 1 $? "$out"

# 6. the 27 tree as built
if [ -r "$dtb27" ] && [ -r "$board27" ]; then
    out=$(python3 "$check" adt "$dtb27" "$board27" --expect-base 0xa600000 2>&1)
    report "27 hardware.dtb against the K60 board table" 1 $? "$out"
else
    echo "SKIP 27 tree not readable at $dtb27"
fi

# 7. sheng's board, same OS version, is the positive control for the board half:
#    it carries the USB prelink roots, so if it also has no [adt.arm-io] block
#    the missing block is a K60 gap rather than a 27-wide absence.
sheng=/mnt/e/hackios/UniXNU-sheng/board.toml
if [ -r "$sheng" ]; then
    echo "INFO sheng board half:"
    python3 "$check" adt "$dtb27" "$sheng" 2>&1 | grep -E 'adt\.arm-io nodes|usb arm-io nodes' | sed 's/^/     /'
else
    echo "SKIP sheng board table not readable"
fi

if [ "$failures" -eq 0 ]; then
    echo "RESULT PASS"
    exit 0
fi
echo "RESULT FAIL ($failures)"
exit 1
