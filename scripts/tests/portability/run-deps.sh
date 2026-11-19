#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host check: is the wiring table in IOS27-WIRING.md complete?
#
# The 27 tree links the glue against a kernel that carries none of our code.
# Every kernel symbol those two files still need is a line somebody has to add
# there, so the set is a contract, not a remark. This runner builds the pair
# that conf/files will carry - PongAudioAmp.c and PongAudioGeniI2c.c - into one
# relocatable object and fails on any undefined symbol the table does not name.
#
#   sh scripts/tests/portability/run-deps.sh
#
# The same loop reads any object, which is how the failure is demonstrated:
#
#   sh scripts/tests/portability/run-deps.sh --object /tmp/unknown.o
#
# Exits 0 and prints "DEPS OK" when the pair only asks for the table.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

object=
if [ $# -gt 0 ]; then
	if [ "$1" != "--object" ] || [ $# -ne 2 ]; then
		echo "usage: run-deps.sh [--object FILE]" >&2
		exit 2
	fi
	object=$2
fi

if [ -n "$object" ]; then
	if [ ! -f "$object" ]; then
		echo "FAIL: no object at $object" >&2
		exit 2
	fi
	pair=$object
else
# The host assembler refuses the arm64 barrier; -c is the point here, so strip it.
for f in PongAudioAmp PongAudioGeniI2c; do
	sed 's/__asm__ volatile("dsb sy" ::: "memory");/\/* barrier removed on the host *\//' \
		"$repo/drivers/PongAudio/$f.c" > "$work/$f.c"
	cc -std=gnu11 -Wall -Wextra -Werror -DXNU_PONG_AUDIO -c -o "$work/$f.o" \
		-I "$here" -I "$repo/drivers/PongAudio" "$work/$f.c"
done
ld -r -o "$work/pair.o" "$work/PongAudioAmp.o" "$work/PongAudioGeniI2c.o"
pair=$work/pair.o
fi

# The table in IOS27-WIRING.md section 1, plus what the host C library and the
# host compiler add on their own (the kernel supplies printf itself, and the
# stack protector is a build flag, not an API).
allowed=" ml_io_map ml_io_map_wcomb PE_parse_boot_argn printf delay_for_interval k60_pmic_glink_send_audio puts stack_chk_fail stack_chk_guard memcpy memset memmove strlen "
# One line, single spaces, so the match below is a plain substring test.
allowed=$(printf '%s' "$allowed" | tr -s '[:space:]' ' ')

bad=
count=0
for sym in $(nm -u "$pair" | sed 's/^ *U //' | sed 's/^_*//' | sort -u); do
	count=$((count + 1))
	case "$allowed" in
	*" $sym "*) ;;
	*) bad="$bad $sym" ;;
	esac
done

if [ -n "$bad" ]; then
	echo "FAIL: the glue needs$bad, which IOS27-WIRING.md section 1 does not name" >&2
	exit 1
fi
echo "DEPS OK undefined=$count, all named in IOS27-WIRING.md"
