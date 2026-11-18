#!/bin/sh
# Host-only regression for the resumable SMC transaction loop.
# K60_MODEM_SCM_TEST replaces only the native smc instruction; the public
# PAS entry points and retry loop in K60ModemPas.c are exercised unchanged.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${K60_TEST_OUT:-/mnt/e/k60-work/artifacts/tests}
mkdir -p "$out"
gcc -std=c11 -O2 -Wall -Wextra -Werror -DK60_MODEM_SCM_TEST -I"$here/.." \
    "$here/test-modem-scm-continuation.c" "$here/../K60ModemPas.c" \
    -o "$out/t-modem-scm-continuation"
"$out/t-modem-scm-continuation"
