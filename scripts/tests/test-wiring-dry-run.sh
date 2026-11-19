#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Walk the wiring of IOS27-WIRING.md in a tree that looks like a 27 tree.
#
# The edits are a sequence: copy the files, list them in bsd/conf/files, compile
# the glue with -DXNU_PONG_AUDIO, and (opt-in) call it once from bsd_init.c. Each piece has its own check, but nothing
# ran them in order against a tree without the 16 series button driver - which is
# exactly the tree the migration lands in. This script builds that tree in a temp
# directory, walks the sequence, and fails at the step that broke.
#
#   sh scripts/tests/test-wiring-dry-run.sh
#
# Prints one line: DRYRUN OK files=23 conf=2 init=1 tests=TESTS OK ...
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tree=$tmp/tree
mkdir -p "$tree/.cache/xnu-work/bsd/conf" "$tree/.cache/xnu-work/bsd/dev" \
	"$tree/.cache/xnu-work/bsd/kern" || exit 1
printf "bsd/dev/vfs_syscalls.c\t\t\tstandard\n" > "$tree/.cache/xnu-work/bsd/conf/files" || exit 1
printf '\tbsd_init_kprintf("calling vfsinit\\n");\n\tvfsinit();\n' \
	> "$tree/.cache/xnu-work/bsd/kern/bsd_init.c" || exit 1
cd "$repo" || exit 1

# 1. the copy
python3 scripts/check-audio-migration.py --copy "$tree/drivers/PongAudio" >"$tmp/copy" 2>&1 || {
	echo "FAIL: the copy refused:"; cat "$tmp/copy"; exit 1; }
cp drivers/PongAudio/PongAudioGeniI2c.c drivers/PongAudio/PongAudioAmp.c "$tree/.cache/xnu-work/bsd/dev/" || exit 1

# 2. the listing: the default anchor must fail, a named anchor must take
if python3 scripts/add-audio-conffiles.py "$tree" >"$tmp/a" 2>&1; then
	echo "FAIL: the button-driver anchor was accepted outside a 16 tree"; exit 1
fi
grep -q 'pass --anchor' "$tmp/a" || { echo 'FAIL: the anchor miss does not say how to fix it'; cat "$tmp/a"; exit 1; }
anchor=$(printf "bsd/dev/vfs_syscalls.c\t\t\tstandard")
python3 scripts/add-audio-conffiles.py --anchor "$anchor" "$tree" >"$tmp/b" 2>&1 || {
	echo "FAIL: the named anchor was refused:"; cat "$tmp/b"; exit 1; }
grep -q 'pong_audio lines 0 -> 2' "$tmp/b" || { echo 'FAIL: the count did not grow'; cat "$tmp/b"; exit 1; }
python3 scripts/add-audio-conffiles.py --check "$tree" >/dev/null 2>&1 || {
	echo "FAIL: check mode disagrees after the write"; exit 1; }

# 3. the call site: nothing runs it until bsd_init names it
if python3 scripts/apply-audio27-wiring.py "$tree" --anchor "$anchor" >"$tmp/c" 2>&1; then
	:
else
	echo "FAIL: the applier refused without the hook:"; cat "$tmp/c"; exit 1
fi
grep -q 'not hooked (pass --hook-init)' "$tmp/c" || {
	echo 'FAIL: a run without the hook does not say the glue never runs'; cat "$tmp/c"; exit 1; }
python3 scripts/apply-audio27-wiring.py "$tree" --anchor "$anchor" --hook-init >"$tmp/d" 2>&1 || {
	echo "FAIL: the hook refused:"; cat "$tmp/d"; exit 1; }
grep -q 'probe calls 0 -> 1' "$tmp/d" || { echo 'FAIL: the hook count did not grow'; cat "$tmp/d"; exit 1; }
init=$(grep -c 'pong_audio_amp_probe()' "$tree/.cache/xnu-work/bsd/kern/bsd_init.c")
[ "$init" = 1 ] || { echo "FAIL: the hook landed $init times"; exit 1; }

# 4. the copy still tests, with the glue in place
out=$(cd "$tree/drivers/PongAudio" && sh tests/run-tests.sh 2>&1 | tail -1)
case "$out" in
	*"TESTS OK"*) ;;
	*) echo "FAIL: the copy does not test: $out"; exit 1;;
esac
lines=$(grep -c PongAudio "$tree/.cache/xnu-work/bsd/conf/files")
files=$(ls "$tree/drivers/PongAudio"/*.c "$tree/drivers/PongAudio"/*.h "$tree/drivers/PongAudio/tests"/* | wc -l | tr -d " ")
echo "DRYRUN OK files=$files conf=$lines init=$init tests=$out"