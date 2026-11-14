#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
#
# Host test for the AP-side amplifier path: the GENI I2C state machine and the
# register map it uses. No device, no kernel headers - the fake engine is a
# 16 KiB register array in the test itself.
#
#   drivers/PongAudio/tests/run-tests.sh
#
# Exits non-zero if any case fails.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
driver=$(CDPATH= cd -- "$here/.." && pwd)
out=${TMPDIR:-/tmp}/test-pong-audio-geni-i2c

cc=${CC:-cc}
"$cc" -std=gnu11 -Wall -Wextra -Werror -I"$driver" \
	-o "$out" \
	"$here/test-pong-audio-geni-i2c.c" \
	"$driver/PongAudioGeniI2c.c" \
	"$driver/PongCodecSwr.c"
exec "$out"
