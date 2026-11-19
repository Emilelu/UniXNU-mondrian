#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# One command for the audio lane's iOS 27 preflight. Nothing here needs a device.
#
#   sh scripts/check-audio27-preflight.sh
#
# Runs, in order:
#   1. the migration list, including the one-guard rule for the driver macro
#   2. the glue against the six-symbol kernel stub set
#   3. the macro itself: three symbols with it, none without
#   4. the glue's link-time needs against the wiring table
#   5. the conf-files appender's host tests (the anchor miss must fail loudly)
#   6. the wiring applier: copy, conf/files and the printed builder line
#   7. the amplifier probe running on the host against a zero page
#   8. the playback judge's host tests
#   9. the amplifier side's host tests (979 cases)
#  10. the three edits walked in order against a tree without the button driver
#  11. the 27 interface checker's own tests
#  12. the four interfaces, against a real 27 XNU tree when one is on disk
#      (XNU27_REPO overrides the search)
#  13. the product checker's own tests, and - when XNU27_KERNEL names a built
#      kernel or boot image - whether that product really carries the audio
#  14. the sheng ABI checker's own tests
#  15. sheng's audio host tests, and its ABI constants at that commit, when its checkout is reachable; the row names
#      the commit it ran on, because a stale checkout passes just as quietly
# Prints one line per check and exits non-zero on the first failure.
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
cd "$repo" || exit 1
fail=0

# Which tree did this measure? A green line that cannot name its commit is the
# same evidence as a green line on the wrong object.
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
sha=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
printf 'repo %s %s @ %s\n' "$repo" "$branch" "$sha"

run()
{
	name=$1
	shift
	out=$("$@" 2>&1)
	rc=$?
	if [ "$rc" -ne 0 ]; then
		printf 'FAIL %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)"
		fail=1
		return
	fi
	printf 'ok   %-34s %s\n' "$name" "$(printf '%s' "$out" | tail -1)"
}

run "migration list + pure C build" python3 scripts/check-audio-migration.py --compile
run "glue vs six kernel symbols" sh scripts/tests/portability/run.sh
run "driver macro really switches it" sh scripts/tests/portability/run-symbols.sh
run "glue needs only the table" sh scripts/tests/portability/run-deps.sh
run "conf-files appender is loud" python3 scripts/tests/test-audio-conffiles.py
run "one command applies the wiring" python3 scripts/tests/test-apply-audio27-wiring.py
run "probe runs on host" sh scripts/tests/portability/run-probe.sh
run "playback judge tests" python3 scripts/tests/test-judge-audio-capture.py
run "amplifier host tests" sh drivers/PongAudio/tests/run-tests.sh
run "three edits dry run" sh scripts/tests/test-wiring-dry-run.sh
run "27 interface checker is honest" python3 scripts/tests/test-audio27-kernel-api.py
run "27 product checker is honest" python3 scripts/tests/test-audio27-kernel.py
run "sheng abi checker is honest" python3 scripts/tests/test-sheng-abi.py

xnu27=${XNU27_REPO:-}
if [ -z "$xnu27" ]; then
	for candidate in /opt/k60/trees/ios27-out/feeds/xnu-* "$repo/../xnu"; do
		if [ -f "$candidate/bsd/conf/files" ] || [ -f "$candidate/.cache/xnu-work/bsd/conf/files" ]; then
			xnu27=$candidate
			break
		fi
		done
fi
if [ -n "$xnu27" ]; then
	run "27 kernel interfaces are there" python3 scripts/check-audio27-kernel-api.py "$xnu27"
else
	printf 'skip %-34s no 27 xnu tree (set XNU27_REPO)\n' "27 kernel interfaces are there"
fi

# The product itself, when there is one: a built 27 kernel or a boot image.
# Strings always decide; symbols decide when the file has a readable symbol table.
if [ -n "${XNU27_KERNEL:-}" ]; then
	run "27 kernel carries the audio" python3 scripts/check-audio27-kernel.py "$XNU27_KERNEL"
else
	printf 'skip %-34s no built kernel (set XNU27_KERNEL)\n' "27 kernel carries the audio"
fi

sheng=${SHENG_REPO:-}
if [ -z "$sheng" ]; then
	for candidate in "$repo/../UniXNU-sheng" /e/hackios/UniXNU-sheng /mnt/e/hackios/UniXNU-sheng; do
		if [ -f "$candidate/scripts/check-audioreach-host.py" ]; then
			sheng=$candidate
			break
		fi
	done
fi
if [ -n "$sheng" ] && [ -f "$sheng/scripts/check-audioreach-host.py" ]; then
	out=$(cd "$sheng" && python3 scripts/check-audioreach-host.py 2>&1)
	rc=$?
	if [ "$rc" -ne 0 ]; then
		printf 'FAIL %-34s %s\n' "sheng audioreach host tests" "$(printf '%s' "$out" | tail -1)"
		fail=1
	else
		sha=$(git -C "$sheng" rev-parse --short HEAD 2>/dev/null || echo unknown)
		printf 'ok   %-34s %s (%s)\n' "sheng audioreach host tests" \
		    "$(printf '%s' "$out" | tail -1)" "$sha"
		run "sheng abi constants hold" python3 scripts/check-sheng-abi.py --sheng "$sheng"
	fi
else
	printf 'skip %-34s no sheng checkout (set SHENG_REPO)\n' "sheng audioreach host tests"
fi

if [ "$fail" -ne 0 ]; then
	echo "PREFLIGHT FAILED"
	exit 1
fi
echo "PREFLIGHT OK"
