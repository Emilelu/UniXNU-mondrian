#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host test for the two-slot QcomGlink prototype.
#
# The transport lives in drivers/PongPower/, which belongs to the battery line
# and keeps one channel slot. The prototype therefore travels as a patch
# (patches/audio/0002-k60-glink-multislot.patch) and this script applies it to
# a throwaway copy before compiling. Nothing here writes to the repository, to
# SMEM or to a device.
#
#   sh drivers/PongAudio/tests/run-glink-multislot-tests.sh
#
# Exits 0 and prints "TESTS OK <n> cases" when every case passes.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
driver=$(cd "$here/.." && pwd)
repo=$(cd "$driver/../.." && pwd)
patch_file=$repo/patches/audio/0002-k60-glink-multislot.patch
src=$repo/drivers/PongPower

[ -f "$patch_file" ] || { echo "missing $patch_file" >&2; exit 1; }

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT INT TERM
mkdir -p "$out/drivers/PongPower"
cp "$src/QcomGlink.h" "$src/QcomGlink.c" "$out/drivers/PongPower/"

# -p1 strips the a/ and b/ prefixes the patch carries.
patch -p1 -s -d "$out" < "$patch_file"

cc -std=gnu11 -Wall -Wextra -Werror -I "$out/drivers/PongPower" \
   -o "$out/test-glink-multislot" \
   "$here/test-glink-multislot.c" "$out/drivers/PongPower/QcomGlink.c"
"$out/test-glink-multislot"
