#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host check: does the kernel glue still build against a six-symbol kernel?
#
# The pure C modules already build with no kernel header at all
# (scripts/check-audio-migration.py --compile). PongAudioAmp.c cannot - it
# includes five kernel headers - so this runner supplies the smallest stubs
# that satisfy those includes and compiles it with -Wall -Wextra -Werror.
# A symbol that disappears from the stub set is a symbol the 27 tree must
# still provide, so this is the portability question asked directly.
#
# The body is selected by XNU_PONG_AUDIO on the 27 tree and by the PONG
# machine configuration on the 16 tree; both must build the same body.
#
#   sh scripts/tests/portability/run.sh
#
# Exits 0 and prints "STUBS OK" when the glue builds both ways.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT INT TERM

# -fsyntax-only, not -c: the file carries arm64 barriers ("dsb sy"), and the host
# assembler refuses them. Parsing, type checking and every warning still run.
for define in -DXNU_PONG_AUDIO -DPONG; do
	cc -std=gnu11 -Wall -Wextra -Werror "$define" -fsyntax-only \
	   -I "$here" -I "$repo/drivers/PongAudio" \
	   "$repo/drivers/PongAudio/PongAudioAmp.c"
done
echo "STUBS OK PongAudioAmp.c (XNU_PONG_AUDIO and PONG)"
