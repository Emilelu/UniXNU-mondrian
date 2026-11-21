#!/usr/bin/env bash
# Offline unit test of the QcomDwc3 UCSI client: the official host test from
# drivers/QcomDwc3/tests/ucsi_host.cpp (docs/zh/porting/usb.md:94-98).
#
# Extracts the catalog-pinned revision into a temporary directory, compiles the
# test with clang++ -std=c++17 -I.. and runs it. No kernel build, no device.
#
#   bash scripts/usb27/ucsi-host-test.sh
#   K60_DWC3_REF=/path/to/QcomDwc3.git bash scripts/usb27/ucsi-host-test.sh
#
# Expected output on success: "PASS", then "RESULT PASS", exit 0.
set -u

REV=e4efe95c903a737e0f5955e5b50a8fb4d2a7d718
REF=${K60_DWC3_REF:-/mnt/e/k60-work/scratch/usb27/refs-QcomDwc3}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if [ ! -d "$REF/.git" ]; then
    echo "FAIL no QcomDwc3 clone at $REF (set K60_DWC3_REF)" >&2
    echo "RESULT FAIL" >&2
    exit 2
fi
if ! git -C "$REF" cat-file -e "$REV^{commit}" 2>/dev/null; then
    echo "FAIL revision $REV not fetched in $REF" >&2
    echo "RESULT FAIL" >&2
    exit 2
fi

git -C "$REF" archive "$REV" | tar -x -C "$WORK" || { echo "FAIL extract" >&2; echo "RESULT FAIL" >&2; exit 2; }
if [ ! -f "$WORK/tests/ucsi_host.cpp" ]; then
    echo "FAIL $REV has no tests/ucsi_host.cpp" >&2
    echo "RESULT FAIL" >&2
    exit 2
fi

CXX=${K60_CXX:-clang++}
echo "revision $REV"
echo "compiler $($CXX --version | head -1)"
( cd "$WORK/tests" && "$CXX" -std=c++17 -Wall -I.. ucsi_host.cpp -o ucsi_host ) || { echo "FAIL compile" >&2; echo "RESULT FAIL" >&2; exit 1; }
"$WORK/tests/ucsi_host"
status=$?
if [ $status -ne 0 ]; then
    echo "RESULT FAIL (exit $status)"
    exit 1
fi
echo "RESULT PASS"
