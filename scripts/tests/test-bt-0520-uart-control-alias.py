#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only checks for the 0520 UART control alias and the exec trace.

Stock BlueTool opens com.apple.uart.bluetooth by default, while bluetoothd and
this port use com.apple.uart.sk.bluetooth.  0520 registers the same transport
under both names and logs the first four arguments of BlueTool and bluetoothd,
because launchd starts them through xpcproxy and the arguments decide which
control is opened.

This test binds the patch bytes and the series tail.  It does not boot a
device, open a control or show that BlueTool connects.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches" / "xnu"
SERIES = PATCHES / "series"
PATCH = PATCHES / "0520-k60-bt-uart-control-alias.patch"

SERIES_COUNT = 240
SERIES_PREFIX_COUNT = 239
SERIES_PREFIX_SHA256 = "1cf9d873f5418c9928a845196c9b4a3f3fe5009f9ab5352cf67e6c2119dff620"
SERIES_238_SHA256 = "4a39a8d2fddf0da93dbcab18a2302c69bab8f34955d56e9172c1a395e8b12e11"
PATCH_SHA256 = "15d553964af34bcaf2555a90b1f73548cdabcd45634f14e1cfc20ee3a663d61a"

HUNKS = [
    "@@ -143,6 +143,7 @@",
    "@@ -391,7 +392,7 @@",
    "@@ -399,7 +400,8 @@",
    "@@ -1310,6 +1310,36 @@",
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
    check(PATCH.is_file(), "0520 patch exists", str(PATCH))
    check(sha256(PATCH) == PATCH_SHA256, "0520 bytes", sha256(PATCH))

    diff = PATCH.read_text(encoding="utf-8")
    for hunk in HUNKS:
        check(hunk in diff, "hunk header", hunk)

    added = [line[1:] for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]

    check(any("kern_ctl_ref ctl_alias;" in line for line in added),
          "the transport keeps a second control reference")
    check(any('"com.apple.uart.bluetooth"' in line and "strlcpy" in line for line in added),
          "the alias control is named com.apple.uart.bluetooth")
    check(any("alias_error=ctl_register(&reg,&bt_sk.ctl_alias)" in line for line in added),
          "the alias is registered through ctl_register")
    check(any("reg.ctl_connect=bt_sk_connect" in line for line in added),
          "the alias shares the transport callbacks")
    check(any("control=%s" in line for line in added),
          "a connect names the control it arrived on")
    check(any("K60ARG" in line for line in added),
          "the exec trace prints the daemon arguments")
    check(any('strcmp(k60_base, "BlueTool")' in line for line in added),
          "BlueTool is traced")
    check(any('strcmp(k60_base, "bluetoothd")' in line for line in added),
          "bluetoothd is traced")
    check(not any("3200000u" in line for line in added),
          "0520 does not touch the transport speed")
    check("bsd/kern/kern_exec.c" in diff and "bsd/dev/qbt/qbt_transport.c" in diff,
          "0520 touches the transport and the exec path")

    lines = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    check(len(lines) >= SERIES_COUNT, "series count", str(len(lines)))
    check(all(line.startswith("0523-") for line in lines[SERIES_COUNT:]),
          "only 0523 may follow 0520", str(lines[SERIES_COUNT:]))
    check(lines[SERIES_PREFIX_COUNT - 1] == "0519-k60-bt-userspace-power-nodes.patch",
          "line 239 is 0519", lines[SERIES_PREFIX_COUNT - 1])
    check(lines[SERIES_COUNT - 1] == "0520-k60-bt-uart-control-alias.patch",
          "line 240 is 0520", lines[SERIES_COUNT - 1])
    prefix_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_PREFIX_COUNT]) + "\n").encode()).hexdigest()
    check(prefix_sha == SERIES_PREFIX_SHA256, "239-line 0500..0519 prefix sha256",
          prefix_sha)
    short_sha = hashlib.sha256(
        ("\n".join(lines[:238]) + "\n").encode()).hexdigest()
    check(short_sha == SERIES_238_SHA256, "238-line 0500..0518 prefix sha256", short_sha)
    check(sha256(PATCHES / "0519-k60-bt-userspace-power-nodes.patch") ==
          "7e547a20a52cdf446b0e38ec376a64057cf4c542c188e25bd1e36df9ac8a63d8",
          "0519 bytes are unchanged")
    check(sha256(PATCHES / "0518-k60-bt-gic-intid.patch") ==
          "c1e2cb96ac79b26089e4a495741165d800ee8e730b0a460ab2e476853809e13f",
          "0518 bytes are unchanged")

    print(f"TESTS OK {checks} cases / 0 failure")


if __name__ == "__main__":
    main()
