#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# The glue is compiled by the 27 build, not by us. A warning that the host
# compilers accept today becomes a dead build the day the 27 tree turns on
# -Werror, so this runs both sources through -Wall -Wextra -Werror twice: the
# driver macro on and off. clang is the compiler that matters on 27, gcc is
# what this host has; when clang is absent the two gcc builds still run.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
sed 's/__asm__ volatile("dsb sy" ::: "memory");//' "$repo/drivers/PongAudio/PongAudioAmp.c" > "$work/Amp.c"
cp "$repo/drivers/PongAudio/PongAudioGeniI2c.c" "$work/Geni.c"
built=0
fail=0
for compiler in cc clang; do
	if ! command -v "$compiler" >/dev/null 2>&1; then
		continue
	fi
	for source in Amp Geni; do
		for macro in -DXNU_PONG_AUDIO ''; do
			if ! "$compiler" -std=gnu11 -c -Wall -Wextra -Werror $macro \
				-I "$here" -I "$repo/drivers/PongAudio" \
				"$work/$source.c" -o "$work/$source.o" 2>"$work/log"; then
				fail=1
				echo "WARNINGS FAILED: $compiler $source $macro"
				sed 's/^/  /' "$work/log" | head -20
			fi
			built=$((built + 1))
		done
	done
done
if [ "$fail" -ne 0 ]; then
	exit 1
fi
echo "WARNINGS OK $built builds, both sources, macro on and off"
