#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host run of the amplifier probe (see run-probe.c). Elides the single arm64
# barrier, builds with -fsanitize=address,undefined, and checks two behaviours:
#
#   gate off: the boot argument is absent, so the probe returns 0 silently
#   gate on:  the probe prints its start line and stops at the first missing
#             hardware answer, naming it
#
#   sh scripts/tests/portability/run-probe.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT INT TERM

sed 's|__asm__ volatile("dsb sy" ::: "memory");|/* arm64 barrier elided for the host run */|' \
	"$repo/drivers/PongAudio/PongAudioAmp.c" > "$out/PongAudioAmp.host.c"
grep -q 'arm64 barrier elided' "$out/PongAudioAmp.host.c"

cc -std=gnu11 -Wall -Wextra -Werror -O1 -g -DPONG \
	-fsanitize=address,undefined -fno-omit-frame-pointer \
	-I "$here" -I "$repo/drivers/PongAudio" \
	"$here/run-probe.c" "$out/PongAudioAmp.host.c" \
	"$repo/drivers/PongAudio/PongAudioGeniI2c.c" -o "$out/probe"

PROBE_GATE=0 timeout 60 "$out/probe" > "$out/off.log" 2>&1 || {
	echo "FAIL probe crashed with the gate off"; tail -5 "$out/off.log"; exit 1; }
if grep -q 'amp probe start' "$out/off.log"; then
	echo "FAIL probe printed its start line with the boot argument absent"; exit 1
fi
grep -q 'PROBE RC 0' "$out/off.log"

PROBE_GATE=1 timeout 60 "$out/probe" > "$out/on.log" 2>&1 || {
	echo "FAIL probe crashed with the gate on"; tail -5 "$out/on.log"; exit 1; }
grep -q 'PongAudio: amp probe start' "$out/on.log"
grep -qE 'PongAudio: amp probe (stop: |done )' "$out/on.log"

if grep -qE 'runtime error|ERROR: AddressSanitizer' "$out/on.log"; then
	echo "FAIL sanitizer reported a defect"; grep -E 'runtime error|ERROR: AddressSanitizer' "$out/on.log" | head -3; exit 1
fi
echo "PROBE OK: $(grep -E 'PongAudio: amp probe (stop|done)' "$out/on.log" | tail -1)"
