#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only checks for the 0519 userland power-node candidate.

On iOS 16 BlueTool powers the controller through /dev/btreset, /dev/btwake
and /dev/btpoweroff, which com.apple.driver.AppleBluetooth (class BTReset)
publishes.  That kext is not part of this kernel, so BlueTool's first power
request fails with ENOENT and it exits before it opens
com.apple.uart.sk.bluetooth.  0519 adds the three nodes as a logging shim and
advertises the 3.0 Mbaud the link actually runs at instead of 3.2 Mbaud, which
the 48 MHz QUPV3 source cannot divide exactly.

This test binds the patch bytes and the series tail.  It does not boot a
device, create a node or prove that BlueTool opens one.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches" / "xnu"
SERIES = PATCHES / "series"
PATCH = PATCHES / "0519-k60-bt-userspace-power-nodes.patch"

PATCH_0518 = "0518-k60-bt-gic-intid.patch"
PATCH_0519 = "0519-k60-bt-userspace-power-nodes.patch"
SERIES_COUNT = 239
SERIES_PREFIX_COUNT = 238
SERIES_PREFIX_SHA256 = "4a39a8d2fddf0da93dbcab18a2302c69bab8f34955d56e9172c1a395e8b12e11"
SERIES_SHA256 = "1cf9d873f5418c9928a845196c9b4a3f3fe5009f9ab5352cf67e6c2119dff620"
PATCH_SHA256 = "7e547a20a52cdf446b0e38ec376a64057cf4c542c188e25bd1e36df9ac8a63d8"

HUNKS = [
    "@@ -18,6 +18,114 @@",
    "@@ -439,6 +547,9 @@",
    "@@ -33,7 +33,11 @@",
]

checks = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        return
    print(f"FAIL {label}: {detail}")
    print(f"TESTS FAILED {checks} cases / 1 failure")
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    check(PATCH.is_file(), "0519 patch exists", str(PATCH))
    diff = PATCH.read_text(encoding="utf-8")
    check(sha256(PATCH) == PATCH_SHA256, "0519 bytes", sha256(PATCH))

    headers = [line for line in diff.splitlines() if line.startswith("@@")]
    check(headers == HUNKS, "0519 hunk headers", str(headers))
    check(diff.count("diff --git ") == 2, "0519 touches two files")
    check("a/bsd/dev/qbt/qbt_transport.c" in diff, "0519 edits qbt_transport.c")
    check("a/iokit/Kernel/MiniBluetooth.cpp" in diff, "0519 edits MiniBluetooth.cpp")

    for name in ("btreset", "btwake", "btpoweroff"):
        check(f'"{name}"' in diff, f"{name} node is published")
    check("cdevsw_add(-1, &bt_power_cdevsw)" in diff, "cdevsw is registered")
    check("devfs_make_node(makedev(major, i)" in diff, "nodes are made by minor")
    check("0666" in diff, "nodes are world-writable for bluetoothd")
    check("bt_power_nodes_register();" in diff, "registration is called at power-on")
    check(".d_ioctl = bt_power_ioctl" in diff, "ioctl is logged")
    check(".d_write = bt_power_write" in diff, "write is drained")
    check("[bluetooth power] %s ioctl" in diff, "ioctl log line is present")
    check("[bluetooth power] %s open" in diff, "open log line is present")

    added = [line for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    check("- #define K60_BT_TRANSPORT_SPEED    3200000u" in diff or
          "-#define K60_BT_TRANSPORT_SPEED    3200000u" in diff,
          "the old 3.2 Mbaud define is removed")
    check(any("#define K60_BT_TRANSPORT_SPEED    3000000u" in line for line in added),
          "transport-speed matches the 3.0 Mbaud link")
    check(not any("3200000u" in line for line in added), "3.2 Mbaud is gone")
    check("#ifdef KERNEL" in diff, "the cdev code is kernel-only")

    lines = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    tail_ok = len(lines) == SERIES_COUNT or (
        len(lines) <= SERIES_COUNT + 2
        and lines[SERIES_COUNT].startswith("0520-")
        and all(line.startswith("0523-") for line in lines[SERIES_COUNT + 1:]))
    check(tail_ok, "series is 239 lines plus at most the 0520 tail",
          f"{len(lines)} lines, last {lines[-1]}")
    check(lines[SERIES_PREFIX_COUNT - 1] == PATCH_0518, "line 238 is 0518",
          lines[SERIES_PREFIX_COUNT - 1])
    check(lines[SERIES_COUNT - 1] == PATCH_0519, "line 239 is 0519",
          lines[SERIES_COUNT - 1])
    prefix_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_PREFIX_COUNT]) + "\n").encode()).hexdigest()
    check(prefix_sha == SERIES_PREFIX_SHA256, "238-line 0516+0517+0518 prefix sha256",
          prefix_sha)
    full_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_COUNT]) + "\n").encode()).hexdigest()
    check(full_sha == SERIES_SHA256, "239-line 0500..0519 prefix sha256", full_sha)
    check(sha256(PATCHES / PATCH_0518) ==
          "c1e2cb96ac79b26089e4a495741165d800ee8e730b0a460ab2e476853809e13f",
          "0518 bytes are unchanged")
    check(sha256(PATCHES / "0509-k60-bt-s3-identity-publish.patch") ==
          "6d92dfe3bae1d96e1974a40a46e61ac9bedfb7b3a56276d0e2f085c3f678a584",
          "0509 bytes are unchanged")
    check(sha256(PATCHES / "0500-k60-bt-qbt-new-files.patch") ==
          "4e6f58d96f1ba06cd8d440feaa7546e3df05519631a8550b96a6441ba69bc0b0",
          "0500 bytes are unchanged")

    print(f"TESTS OK {checks} cases / 0 failure")


if __name__ == "__main__":
    main()
