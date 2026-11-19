#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host check: does the driver macro actually switch the glue on?
#
# PongAudioAmp.c is one #if around the whole body. With the macro off it still
# compiles - to an empty translation unit, which is how the 27 tree would end
# up with zero PongAudio lines while every gate stayed green. This runner
# compiles the file with code generation (the arm64 barrier is stripped, the
# host assembler refuses it) and counts the symbols the object exports:
#
#   no macro                     0 symbols
#   -DXNU_PONG_AUDIO (27 line)   the three entry points
#   -DPONG (16 line, machine)    the same three
#
#   sh scripts/tests/portability/run-symbols.sh        # host triplicate
#
# The same script reads a real object, which is the check that matters on the
# 27 tree: the kernel build makes a Mach-O object, llvm-nm-18 prints the probe
# entry point with a leading underscore, and both directions have to be shown:
#
#   NM=llvm-nm-18 sh scripts/tests/portability/run-symbols.sh \
#       --object .cache/xnu-work/EXPORT/.../PongAudioAmp.o --expect on
#   NM=llvm-nm-18 sh scripts/tests/portability/run-symbols.sh \
#       --object <object built without the macro> --expect off
#
# A count of one is the pass mark for "--expect on"; anything else means the
# macro never reached the compile, and the log would still look healthy.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
nm_bin=${NM:-nm}
object=
expect=
while [ $# -gt 0 ]; do
	case "$1" in
	--object) object=$2; shift 2 ;;
	--expect) expect=$2; shift 2 ;;
	*) echo "usage: run-symbols.sh [--object FILE --expect on|off]" >&2; exit 2 ;;
	esac
done

probe_count()
{
	# Matches 'T pong_audio_amp_probe' (ELF) and 'T _pong_audio_amp_probe' (Mach-O).
	"$nm_bin" -g --defined-only "$1" | grep -c 'pong_audio_amp_probe$' || true
}

if [ -n "$object" ]; then
	if [ ! -f "$object" ]; then
		echo "FAIL: no object at $object" >&2
		exit 2
	fi
	probe=$(probe_count "$object")
	case "$expect" in
	on)
		if [ "$probe" -lt 1 ]; then
			echo "FAIL: $object exports no pong_audio_amp_probe; the macro never reached the compile"
			exit 1
		fi ;;
	off)
		if [ "$probe" -ne 0 ]; then
			echo "FAIL: $object exports $probe probe symbol(s) without the macro"
			exit 1
		fi ;;
	*)
		echo "FAIL: --object needs --expect on|off" >&2
		exit 2 ;;
	esac
	echo "SYMBOLS OK object=$object expect=$expect probe=$probe"
	exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

# -c needs the assembler, so drop the one barrier instead of -fsyntax-only.
sed 's/__asm__ volatile("dsb sy" ::: "memory");/\/* barrier removed on the host *\//' \
	"$repo/drivers/PongAudio/PongAudioAmp.c" > "$work/PongAudioAmp.c"

count()
{
	name=$1
	shift
	cc -std=gnu11 -Wall -Wextra -Werror "$@" -c -o "$work/$name.o" \
		-I "$here" -I "$repo/drivers/PongAudio" "$work/PongAudioAmp.c"
	"$nm_bin" -g --defined-only "$work/$name.o" | wc -l | tr -d ' '
}

off=$(count off)
on27=$(count on27 -DXNU_PONG_AUDIO)
on16=$(count on16 -DPONG)

if [ "$off" -ne 0 ]; then
	echo "FAIL: without the macro the object exports $off symbol(s), expected 0"
	"$nm_bin" -g --defined-only "$work/off.o" || true
	exit 1
fi
for name in on27 on16; do
	eval "n=\$$name"
	if [ "$n" -lt 3 ]; then
		echo "FAIL: $name exports $n symbol(s), expected the three entry points"
		exit 1
	fi
	if [ "$(probe_count "$work/$name.o")" -lt 1 ]; then
		echo "FAIL: $name has no pong_audio_amp_probe in its symbol table"
		exit 1
	fi
done
echo "SYMBOLS OK off=0 XNU_PONG_AUDIO=$on27 PONG=$on16"
