#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only checks for the 0525 boot-argument aliases.

The official Bluetooth porting contract enables the driver with
`bluetooth=1` and caps logging with `log-bluetooth=2`; this board has
always used `k60bt=1` and a fixed level of three.  0525 accepts both
spellings (k60bt wins when present), makes the log cap configurable and
keeps the default at three so earlier flights keep the same output.

This test binds the patch bytes and the series tail.  It does not boot a
device and does not parse a real boot argument.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches" / "xnu"
SERIES = PATCHES / "series"
PATCH = PATCHES / "0525-k60-bt-official-boot-args.patch"

SERIES_COUNT = 242
SERIES_PREFIX_COUNT = 241
SERIES_SHA256 = "ad158cf5a72746d7a6645c96e40afe7bbb8c826e258ebcb380396a60f5a23fca"
SERIES_PREFIX_SHA256 = "c1e23a54a5b1a4ba3fed3efef47b5f5650f246e9d14b39dc3a35195dd638c03d"
PATCH_SHA256 = "411b2a3db607697885ea68f03bb1900e1dde565c38787a211fe2d63819d9c8c8"

HUNKS = [
    "@@ -1595,12 +1595,17 @@",
    "@@ -2200,8 +2205,21 @@",
    "@@ -126,7 +126,11 @@",
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
    check(PATCH.is_file(), "0525 patch exists", str(PATCH))
    check(sha256(PATCH) == PATCH_SHA256, "0525 bytes", sha256(PATCH))

    diff = PATCH.read_text(encoding="utf-8")
    for hunk in HUNKS:
        check(hunk in diff, "hunk header", hunk)

    added = [line[1:] for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    body = "\n".join(added)
    check("static int k60_log_level = 3;" in body,
          "the log cap defaults to three")
    check(body.count("if (level <= k60_log_level)") == 2,
          "both log sinks honour the cap")
    check('PE_parse_boot_argn("log-bluetooth"' in body,
          "log-bluetooth is parsed")
    check("level > 6u ? 6 : (int)level" in body,
          "the log level is clamped to six")
    check(body.count('PE_parse_boot_argn("bluetooth"') == 2,
          "both gates accept bluetooth=")
    check("k60bt stays the K60 spelling and wins when present" in body,
          "the alias does not replace k60bt")
    check("boot: log-bluetooth=%d" in body,
          "the accepted level is logged")

    check("bsd/dev/qbt_k60.c" in diff and
          "iokit/Kernel/MiniBluetooth.cpp" in diff,
          "0525 touches the board backend and the publish gate")
    check("kern_exec.c" not in diff and "qbt_transport" not in diff,
          "0525 touches nothing else")
    check("3200000u" not in diff,
          "0525 does not touch the published transport speed")

    lines = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    check(len(lines) >= SERIES_COUNT, "series count", str(len(lines)))
    check(lines[SERIES_COUNT - 1] == "0525-k60-bt-official-boot-args.patch",
          "line 242 is 0525", lines[SERIES_COUNT - 1])
    check(lines[SERIES_PREFIX_COUNT - 1] == "0523-k60-bt-transport-set-rate.patch",
          "line 241 is still 0523", lines[SERIES_PREFIX_COUNT - 1])
    check(len(lines) == SERIES_COUNT, "no entry follows 0525",
          " ".join(lines[SERIES_COUNT:]))
    series_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_COUNT]) + "\n").encode()).hexdigest()
    check(series_sha == SERIES_SHA256, "242-line series sha256", series_sha)
    prefix_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_PREFIX_COUNT]) + "\n").encode()).hexdigest()
    check(prefix_sha == SERIES_PREFIX_SHA256, "241-line 0500..0523 prefix sha256",
          prefix_sha)
    check(sha256(PATCHES / "0523-k60-bt-transport-set-rate.patch") ==
          "8240dcbf0fc9563a4cae6b6405278553ab4689a6760c919421448d65d8ee8575",
          "0523 bytes are unchanged")
    check(sha256(PATCHES / "0520-k60-bt-uart-control-alias.patch") ==
          "15d553964af34bcaf2555a90b1f73548cdabcd45634f14e1cfc20ee3a663d61a",
          "0520 bytes are unchanged")

    print(f"TESTS OK {checks} cases / 0 failure")


if __name__ == "__main__":
    main()
