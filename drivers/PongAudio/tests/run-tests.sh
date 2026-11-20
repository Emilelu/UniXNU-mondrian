#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
#
# Host test for the AP-side amplifier path: the GENI I2C state machine and the
# register map it uses. No device, no kernel headers - the fake engine is a
# 16 KiB register array in the test itself.
#
#   drivers/PongAudio/tests/run-tests.sh [workdir]
#
# workdir is optional. A caller that owns a directory passes it and keeps it;
# without one the script makes a private directory and removes it.
#
# Exits non-zero if any case fails.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
driver=$(CDPATH= cd -- "$here/.." && pwd)
case $# in
0)
	work=$(mktemp -d "${TMPDIR:-/tmp}/test-pong-audio-geni-i2c.XXXXXX")
	own=1
	;;
1)
	work=$1
	own=0
	;;
*)
	echo "usage: $0 [workdir]" >&2
	exit 2
	;;
esac
mkdir -p "$work"
if [ "$own" = 1 ]; then
	trap 'rm -rf "$work"' EXIT HUP INT TERM
fi
out=$work/test-pong-audio-geni-i2c

cc=${CC:-cc}
"$cc" -std=gnu11 -Wall -Wextra -Werror -I"$driver" \
	-o "$out" \
	"$here/test-pong-audio-geni-i2c.c" \
	"$driver/PongAudioGeniI2c.c" \
	"$driver/PongCodecSwr.c" \
	"$driver/PongCodecLpi.c" \
	"$driver/PongCodecMacro.c" \
	"$driver/PongCodecProbe.c"
"$out"
