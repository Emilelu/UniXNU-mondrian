#!/usr/bin/env bash
# The host test suite: every K60 driver test that can run without a kernel.
#
# This lived in /mnt/e/k60-work/artifacts/run-host-tests.sh for weeks, which is
# exactly the shape iron rule 5 forbids: a check that passes but is not in the
# repository is invisible to whoever reads the repository, and a scratch cleanup
# takes it away. It is also the only thing that compiled the 27-line sources
# before P-269, so it is a gate, not a convenience.
#
#   bash scripts/run-host-tests.sh [--list]
#
# K60_HOST_TEST_OUT overrides where the binaries go (default build/host-tests).
# A test whose driver source is not in this checkout is skipped and counted, not
# failed: the same file runs on the 16 line and the 27 line, which do not carry
# the same drivers.
set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT=${K60_HOST_TEST_OUT:-$REPO/build/host-tests}
mkdir -p "$OUT"

# name | extra flags | sources (first is the test itself)
TESTS=(
"modem-bringup|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-modem-bringup.c drivers/PongCellular/K60ModemBoot.c drivers/PongCellular/K60ModemImage.c"
"modem-pas|-Idrivers/PongCellular|scripts/tests/test-k60-modem-pas.c"
"modem-assign|-Idrivers/PongCellular|scripts/tests/test-k60-modem-assign.c"
"modem-rmtfs|-Idrivers/PongCellular|scripts/tests/test-k60-rmtfs.c drivers/PongCellular/K60ModemRmtfs.c"
"modem-qrtr|-Idrivers/PongCellular|scripts/tests/test-k60-modem-qrtr.c drivers/PongCellular/K60ModemQrtr.c"
"modem-memshare|-Idrivers/PongCellular|scripts/tests/test-k60-memshare.c drivers/PongCellular/K60ModemMemshare.c"
"modem-smp2p|-Idrivers/PongCellular|scripts/tests/test-k60-modem-smp2p.c"
"modem-sysmon|-Idrivers/PongCellular|scripts/tests/test-k60-sysmon.c drivers/PongCellular/K60ModemSysmon.c"
"efs|-Idrivers/PongCellular|scripts/tests/test-k60-efs.c drivers/PongCellular/K60ModemEfs.c drivers/PongCellular/K60ModemRmtfs.c"
"pmic-rail|-Idrivers/PongPower|scripts/tests/test-k60-pmic-rail.c drivers/PongPower/K60PmicRail.c"
"ipa|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa.c drivers/PongCellular/K60Ipa.c drivers/PongCellular/K60Mdt.c"
"mdt|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-mdt.c drivers/PongCellular/K60Ipa.c drivers/PongCellular/K60Mdt.c"
"ipa-gsi|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-gsi.c drivers/PongCellular/K60Ipa.c drivers/PongCellular/K60IpaGsi.c drivers/PongCellular/K60Mdt.c"
"ipa-smmu|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-smmu.c drivers/PongCellular/K60IpaSmmu.c"
"ipa-qmap|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-qmap.c drivers/PongCellular/K60IpaQmap.c"
"ipa-qmi|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-qmi.c drivers/PongCellular/K60IpaQmi.c"
"ipa-qmi-server|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-qmi-server.c drivers/PongCellular/K60IpaQmiServer.c drivers/PongCellular/K60IpaQmi.c"
"ipa-qmi-transport|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-qmi-transport.c drivers/PongCellular/K60IpaQmiTransport.c drivers/PongCellular/K60IpaQmiServer.c drivers/PongCellular/K60IpaQmi.c"
"ipa-qrtr|-DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-qrtr.c drivers/PongCellular/K60IpaQrtr.c drivers/PongCellular/K60IpaQmiTransport.c drivers/PongCellular/K60IpaQmiServer.c drivers/PongCellular/K60IpaQmi.c drivers/PongCellular/K60ModemQrtr.c"
"ipa-runtime-ceiling|-std=c11 -DK60_HOST_TEST -Idrivers/PongCellular|scripts/tests/test-k60-ipa-runtime-ceiling.c"
"arm-smmu|-Idrivers/PongAdreno/ArmSmmu4K|scripts/tests/test-k60-arm-smmu.c drivers/PongAdreno/ArmSmmu4K/ArmSmmu4K.c drivers/PongAdreno/ArmSmmu4K/ArmSmmu4KContext.c"
)

# name | command (the test writes its own PASS line)
PY_TESTS=(
"ipa-patch|scripts/tests/test-k60-ipa-patch.py"
"modem-ipa-fw|scripts/tests/test-k60-modem-ipa-fw.py --selftest"
"flight-log|scripts/tests/test-check-modem-flight-log.py"
"flight-judge|scripts/judge-cellular-flight.py --self-test"
"flight-fixtures|scripts/tests/test-k60-flight-fixtures.py"
"pitfall-id|scripts/next-pitfall-id.py --self-test"
"port27|scripts/port-cellular-to-xnu27.py --self-test"
"readiness27|scripts/check-ios27-readiness.py --self-test"
"symbols27|scripts/check-ios27-symbols.py --self-test"
"placement27|scripts/check-call-site-placement.py --self-test"
"fly|scripts/fly-cellular.py --self-test"
)

if [ "${1:-}" = "--list" ]; then
	printf '%s\n' "${TESTS[@]}" | cut -d'|' -f1
	printf '%s\n' "${PY_TESTS[@]}" | cut -d'|' -f1
	exit 0
fi

cd "$REPO" || exit 1
ran=0
skipped=0
failed=0

for entry in "${TESTS[@]}"; do
	name=${entry%%|*}
	rest=${entry#*|}
	flags=${rest%%|*}
	sources=${rest#*|}
	missing=
	for source in $sources; do
		[ -f "$source" ] || missing="$source"
	done
	if [ -n "$missing" ]; then
		echo "K60 HOST skip $name: $missing is not in this checkout"
		skipped=$((skipped + 1))
		continue
	fi
	# shellcheck disable=SC2086
	if ! gcc -O1 -Wall -Wextra -Werror $flags -o "$OUT/t-$name" $sources; then
		echo "K60 HOST FAIL $name does not build"
		failed=$((failed + 1))
		continue
	fi
	if ! "$OUT/t-$name"; then
		echo "K60 HOST FAIL $name does not pass"
		failed=$((failed + 1))
		continue
	fi
	ran=$((ran + 1))
done

for entry in "${PY_TESTS[@]}"; do
	name=${entry%%|*}
	command=${entry#*|}
	script=${command%% *}
	if [ ! -f "$script" ]; then
		echo "K60 HOST skip py-$name: $script is not in this checkout"
		skipped=$((skipped + 1))
		continue
	fi
	# shellcheck disable=SC2086
	if ! PYTHONIOENCODING=utf-8 python3 $command; then
		echo "K60 HOST FAIL py-$name"
		failed=$((failed + 1))
		continue
	fi
	ran=$((ran + 1))
done

if [ "$failed" -gt 0 ]; then
	echo "K60 HOST FAILED $failed of $((ran + failed)) suite(s), $skipped skipped"
	exit 1
fi
echo "K60 HOST PASS $ran suite(s), $skipped skipped, binaries in $OUT"
