#!/usr/bin/env python3
"""P-316: the boot image must carry the *patched* kernel, not the raw build product.

The 2026-11-24 builds showed the failure mode: `unixnu build payload` patched its
own staged copy, then `k60-kernel-swap.py` copied `$BOARD_DIR/kernel/kernel.macho`
(the unpatched product) over both the payload and the boot ramdisk.  Every
`check-ios27-artifacts.py` run then reported "payload kernel.macho is not the
declared transform ... at 0x15f2bac".  The fix is a stable patched copy made once
in the kernel stage and used by both consumers; this test keeps that wiring.
"""
import pathlib
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "build-ios27-linux.sh"


def main():
    text = SCRIPT.read_text()
    failures = []
    if "PATCHED_KERNEL=\"$BOARD_DIR/kernel/kernel.patched.macho\"" not in text:
        failures.append("no PATCHED_KERNEL variable")
    if 'patch-armcpu-validate.py" "$PATCHED_KERNEL" --apply' not in text:
        failures.append("the patched copy is never produced")
    if 'SWAP_KERNEL="$BOARD_DIR/kernel/kernel.patched.macho"' not in text:
        failures.append("the swap does not start from the patched copy")
    swap = text.split('k60-kernel-swap.py', 1)[-1][:300]
    if '--kernel "$BOARD_DIR/kernel/kernel.macho"' in swap:
        failures.append("the swap still points at the raw kernel product")
    for failure in failures:
        print("FAIL", failure)
    print("TESTS OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
