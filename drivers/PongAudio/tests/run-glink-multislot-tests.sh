#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Host test for the two-slot QcomGlink transport.
#
# The transport in drivers/PongPower/ carries two channel slots: the leased
# PMIC endpoint the battery stack opens, and the audio GPR channel adsp_apps.
# This runner compiles the real source directly; it does not patch a copy and
# never writes to the repository, SMEM or a device.
#
#   sh drivers/PongAudio/tests/run-glink-multislot-tests.sh
#
# Exits 0 and prints "TESTS OK <n> cases" when every case passes.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src=$(cd "$here/../../PongPower" && pwd)

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT INT TERM

cc -std=gnu11 -Wall -Wextra -Werror -I "$src" -o "$out/test-glink-multislot" "$here/test-glink-multislot.c" "$src/QcomGlink.c"
"$out/test-glink-multislot"
