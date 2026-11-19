#!/usr/bin/env python3
"""Check a built kernel and payload for the K60 Bluetooth contract.

The porting page's step 6 asks for the Bluetooth checks that match the board.
This board has no QcaBluetooth userspace model to drive, so the kernel half is
verifiable straight from the artifacts:

  * the kernel carries the UART.SK control names, the power and transport log
    prefixes, the three sysctls QcaBluetooth's BlueTool reads, and the radio
    service class name;
  * the payload's ADT carries the static Bluetooth node exported from
    dts/mondrian.dts.

Usage:
  scripts/check-bluetooth-kernel.py --kernel kernel.macho
  scripts/check-bluetooth-kernel.py --kernel kernel.macho --payload payload.img
  scripts/check-bluetooth-kernel.py --kernel kernel.macho --require log-bluetooth
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

KERNEL_NEEDLES = [
    (b"com.apple.uart.sk.bluetooth", "UART.SK control name"),
    (b"com.apple.uart.bluetooth", "UART control alias"),
    (b"[bluetooth power]", "power node log prefix"),
    (b"[bluetooth sk]", "channel log prefix"),
    (b"qbt_power_on", "kern.qbt_power_on sysctl"),
    (b"qbt_boot", "kern.qbt_boot sysctl"),
    (b"qbt_firmware", "kern.qbt_firmware sysctl"),
    (b"K60BluetoothRadio", "radio IOService class"),
    (b"mac-address-bluetooth0", "/chosen identity key"),
]

# 0526/0527 mount the staged runtime over the sealed system.  They live inside the
# XNU_OWNER_DATA_MOUNT block, so a stage-0 kernel that does not mount Data does not
# carry them at all; --expect-runtime asserts them once that gate is on.
RUNTIME_NEEDLES = [
    (b"/private/var/ngpu/bluetooth-lib", "library overlay source"),
    (b"/private/var/ngpu/bluetooth-bin", "executables overlay source"),
    (b"/System/Library/xpc/launchd.plist", "launchd cache overlay target"),
    (b"[bluetooth-runtime] ", "runtime mount log line"),
]

ADT_NEEDLES = [
    (b"bluetooth", "arm-io/bluetooth node"),
    (b"qcom,wcn6855-bt", "compatible"),
    (b"transport-encoding", "transport-encoding property"),
    (b"transport-speed", "transport-speed property"),
]


def check(data, needles, prefix, failures):
    for needle, what in needles:
        if needle in data:
            print(f"PASS {prefix}{what}: {needle.decode()}")
        else:
            failures.append(f"{prefix}{what}: missing {needle.decode()!r}")
            print(f"FAIL {prefix}{what}: {needle.decode()} not found")


def adt_bytes(payload):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "adt"
        r = subprocess.run(
            ["mcopy", "-n", "-i", str(payload), "::/EFI/UniXNU/Payloads/kernel.macho.adt", str(out)],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"check-bluetooth-kernel: cannot read the ADT: {r.stderr.strip()}")
        return out.read_bytes()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kernel", type=Path, required=True, help="built kernel.macho")
    p.add_argument("--payload", type=Path, help="built payload.img; adds the ADT checks")
    p.add_argument("--expect-runtime", action="store_true",
                   help="also require the 0526/0527 runtime mounts (needs CONFIG_XNU_OWNER_DATA_MOUNT=y)")
    p.add_argument("--require", action="append", default=[],
                   help="extra text the kernel must carry, for a patch the series only adds later")
    a = p.parse_args()
    failures = []
    kernel = a.kernel.read_bytes()
    check(kernel, KERNEL_NEEDLES, "kernel:", failures)
    if a.expect_runtime:
        check(kernel, RUNTIME_NEEDLES, "runtime:", failures)
    for extra in a.require:
        check(kernel, [(extra.encode(), "required text")], "kernel:", failures)
    if a.payload:
        check(adt_bytes(a.payload), ADT_NEEDLES, "adt:", failures)
    if failures:
        print(f"bluetooth-kernel-check: {len(failures)} failure(s)")
        return 1
    print("bluetooth-kernel-check: OK (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
