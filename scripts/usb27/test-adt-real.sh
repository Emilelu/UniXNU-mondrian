#!/usr/bin/env bash
# Exercise the ADT declaration check on the real 27 device tree.
#
# The check itself is static (kc-surface.py adt). This script only proves it
# discriminates: the production dtb gives its verdict, a copy that declares the
# controller the way devicetree.py exports it passes, and copies that break one
# rule each fail. Every copy is derived from the production dtb, so the case
# shapes are the board's own, not a synthetic tree.
#
# Usage:
#   bash scripts/usb27/test-adt-real.sh [DTB] [BOARD_TOML]
# Defaults: the 27 build output dtb and the K60 board table.
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
DTB=${1:-/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/device-tree/hardware.dtb}
BOARD=${2:-/mnt/e/hackios/k60-gates/board.toml}

TMP=${TMPDIR:-/tmp}/usb27-adt-real.$$
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

fail=0
ok() { printf 'PASS %s (exit %s)\n' "$1" "$2"; }
bad() { printf 'FAIL %s (exit %s)\n' "$1" "$2"; fail=$((fail + 1)); }

command -v dtc >/dev/null || { echo "FAIL dtc not found"; exit 2; }
[ -r "$DTB" ] || { echo "FAIL cannot read $DTB"; exit 2; }
[ -r "$BOARD" ] || { echo "FAIL cannot read $BOARD"; exit 2; }

printf 'INFO dtb   %s\n' "$DTB"
printf 'INFO dtb sha256 %s\n' "$(sha256sum "$DTB" | cut -d' ' -f1)"
printf 'INFO board %s\n' "$BOARD"

# dtc decompiles the production dtb once; the variants are cut from that text.
# keep=0 drops the unixnu,adt-name line so the node stops being exported; base
# moves the reg window.
dtc -I dtb -O dts -o "$TMP/real.dts" "$DTB" 2>"$TMP/dtc-decompile.log" || {
	echo "FAIL dtc could not decompile $DTB"; sed -n '1,5p' "$TMP/dtc-decompile.log"; exit 2; }

variant() {  # $1 name  $2 base  $3 keep-adt-name(1|0)
	python3 - "$TMP/real.dts" "$TMP/$1.dts" "$2" "$3" <<'PY'
import pathlib
import sys

src, dst, base, keep = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
text = src.read_text()
node = ['\tusb@a600000 {',
        '\t\tcompatible = "qcom,dwc-usb3-msm", "snps,dwc3";',
        '\t\treg = <0x00 %s 0x00 0xd93c>;' % base]
if keep == '1':
	node.append('\t\tunixnu,adt-name = "usb0";')
node.append('\t};')
lines = text.rstrip('\n').split('\n')
if lines[-1].strip() != '};':
	raise SystemExit('unexpected dtc output tail: %r' % lines[-1])
lines[-1:] = node + ['};']
dst.write_text('\n'.join(lines) + '\n')
PY
	dtc -I dts -O dtb -o "$TMP/$1.dtb" "$TMP/$1.dts" 2>"$TMP/$1.log" || {
		echo "FAIL dtc could not build variant $1"; sed -n '1,5p' "$TMP/$1.log"; return 1; }
	return 0
}

boardcopy() {  # $1 name  $2 arm-io child name  $3 base
	cp "$BOARD" "$TMP/$1.toml"
	{
		echo
		echo "[adt.arm-io.\"$2\".u64]"
		echo "\"dwc-base\" = \"$3\""
		echo "\"dwc-size\" = \"0xd93c\""
		echo
		echo "[adt.arm-io.\"$2\".string]"
		echo "\"compatible\" = \"qcom,dwc-usb3-msm\""
	} >>"$TMP/$1.toml"
}

run() {  # $1 label  $2 want(0|1)  $3 dtb  $4 board  $5.. extra args
	local label=$1 want=$2 dtb=$3 board=$4
	shift 4
	python3 "$HERE/kc-surface.py" adt "$dtb" "$board" "$@" >"$TMP/out.txt" 2>&1
	local rc=$?
	if [ "$rc" -eq "$want" ]; then
		ok "$label" "$rc"
	else
		bad "$label (want $want)" "$rc"
	fi
	sed -n 's/^  REASON /     reason: /p' "$TMP/out.txt"
}

echo "--- 1. production dtb against the production board table"
run "27 hardware.dtb declares no usb child" 1 "$DTB" "$BOARD" --expect-base 0xa600000

echo "--- 2. the controller declared through the board table only"
boardcopy board-usb pong-usb 0xa600000
run "board [adt.arm-io.pong-usb] alone declares it" 0 "$DTB" "$TMP/board-usb.toml" --expect-base 0xa600000

echo "--- 3. the controller declared through an exported device tree node"
variant usb-ok 0xa600000 1 || exit 2
run "exported usb node at 0xa600000 passes" 0 "$TMP/usb-ok.dtb" "$BOARD" --expect-base 0xa600000

echo "--- 4. same node, wrong window"
variant usb-badbase 0xa700000 1 || exit 2
run "usb node at 0xa700000 fails on the expected base" 1 "$TMP/usb-badbase.dtb" "$BOARD" --expect-base 0xa600000

echo "--- 5. same node, but not exported"
variant usb-noname 0xa600000 0 || exit 2
run "usb node without unixnu,adt-name is not a declaration" 1 "$TMP/usb-noname.dtb" "$BOARD" --expect-base 0xa600000

echo "--- 6. both paths name the same child"
boardcopy board-usb0 usb0 0xa600000
run "a name on both sides is refused" 1 "$TMP/usb-ok.dtb" "$TMP/board-usb0.toml"

echo
if [ "$fail" -eq 0 ]; then
	echo "RESULT PASS"
	exit 0
fi
echo "RESULT FAIL ($fail)"
exit 1
