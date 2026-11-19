#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host check: does the driver macro actually switch the glue on?
#
# PongAudioAmp.c is one #if around the whole body. With the macro off it still
# compiles -- to an empty translation unit, which is how the 27 tree would end
# up with zero PongAudio lines while every gate stayed green. This runner
# compiles the file with code generation (the arm64 barrier is stripped, the
# host assembler refuses it) and counts the symbols the object exports:
#
#   no macro                     0 symbols
#   -DXNU_PONG_AUDIO (27 line)   the three entry points
#   -DPONG (16 line, machine)    the same three
#
#   sh scripts/tests/portability/run-symbols.sh
#
# Exits 0 and prints "SYMBOLS OK ..." when all three hold.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

# -c needs the assembler, so drop the one barrier instead of -fsyntax-only.
sed 's/__asm__ volatile("dsb sy" ::: "memory");/\/\* barrier removed on the host \*\//' \
	"$repo/drivers/PongAudio/PongAudioAmp.c" > "$work/PongAudioAmp.c"

count()
{
	name=$1
	shift
	cc -std=gnu11 -Wall -Wextra -Werror "$@" -c -o "$work/$name.o" \
		-I "$here" -I "$repo/drivers/PongAudio" "$work/PongAudioAmp.c"
	nm -g --defined-only "$work/$name.o" | wc -l | tr -d ' '
}

off=$(count off)
on27=$(count on27 -DXNU_PONG_AUDIO)
on16=$(count on16 -DPONG)

if [ "$off" -ne 0 ]; then
	echo "FAIL: without the macro the object exports $off symbol(s), expected 0"
	nm -g --defined-only "$work/off.o" || true
	exit 1
fi
for name in on27 on16; do
	eval "n=\$$name"
	if [ "$n" -lt 3 ]; then
		echo "FAIL: $name exports $n symbol(s), expected the three entry points"
		exit 1
	fi
	if ! nm -g --defined-only "$work/$name.o" | grep -q ' T pong_audio_amp_probe$'; then
		echo "FAIL: $name has no pong_audio_amp_probe in its symbol table"
		exit 1
	fi
done
echo "SYMBOLS OK off=0 XNU_PONG_AUDIO=$on27 PONG=$on16"
