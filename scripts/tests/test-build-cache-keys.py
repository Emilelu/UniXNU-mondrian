#!/usr/bin/env python3
"""P-317/318/319: every cache key and every fast path must cover what it reads.

The 2026-11-24 builds reused a Darwin 22 firmware volume inside a Darwin 23
build twice over: the firmware key ignored uncommitted header edits (P-317),
the boot image key ignored the volume bytes (P-318), and the kernel-swap fast
path never repacked the volume at all (P-319).
"""
import pathlib
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "build-ios27-linux.sh"


def main():
    text = SCRIPT.read_text()
    failures = []
    if "git -C \"$UNIXNU_UEFI\" diff HEAD --binary" not in text:
        failures.append("the firmware key ignores uncommitted uefi changes")
    if text.count('-z "${fw_rebuilt:-}"') < 2:
        failures.append("fw_rebuilt does not guard both the bootimg reuse and the kernel swap")
    if 'if [ -z "${K60_NO_KERNEL_SWAP:-}" ] && [ -z "${fw_rebuilt:-}" ]' not in text:
        failures.append("the kernel-swap path still runs after a firmware rebuild")
    if 'if [ -z "${K60_FORCE_BOOTIMG:-}" ] && [ -z "${fw_rebuilt:-}" ]' not in text:
        failures.append("bootimg reuse still ignores fw_rebuilt")
    for failure in failures:
        print("FAIL", failure)
    print("TESTS OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
