#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# One command for the audio lane's iOS 27 preflight. Nothing here needs a device.
#
#   sh scripts/check-audio27-preflight.sh
#
# Runs, in order:
#   1. the migration list against the driver directory and the five pure C units
#   2. the glue against the six-symbol kernel stub set
#   3. the conf-files appender's own host tests (the anchor miss must fail loudly,
#      and the playback judge's host tests
#   4. the amplifier side's host tests (979 cases)
#   5. sheng's audio host tests, when its checkout is reachable
# Prints one line per check and exits non-zero on the first failure.
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
cd "$repo" || exit 1
fail=0

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
run "conf-files appender is loud" python3 scripts/tests/test-audio-conffiles.py
run "probe runs on host" sh scripts/tests/portability/run-probe.sh
run "playback judge tests" python3 scripts/tests/test-judge-audio-capture.py
run "amplifier host tests" sh drivers/PongAudio/tests/run-tests.sh

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
		printf 'ok   %-34s %s\n' "sheng audioreach host tests" "$(printf '%s' "$out" | tail -1)"
	fi
else
	printf 'skip %-34s no sheng checkout (set SHENG_REPO)\n' "sheng audioreach host tests"
fi

if [ "$fail" -ne 0 ]; then
	echo "PREFLIGHT FAILED"
	exit 1
fi
echo "PREFLIGHT OK"
