#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only checks for the 0523 transport speed hook.

A client TIOCSETA used to be accepted only at the bring-up speed and the
request was merely remembered.  0523 adds the board set_rate hook, has the
worker reclock the GENI engine (the engine owner), and makes the client wait
for the result before the transport reports success.

This test binds the patch bytes and the series tail.  It does not boot a
device, open a control or reclock hardware.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches" / "xnu"
SERIES = PATCHES / "series"
PATCH = PATCHES / "0523-k60-bt-transport-set-rate.patch"

SERIES_COUNT = 241
SERIES_PREFIX_COUNT = 240
SERIES_SHA256 = "c1e23a54a5b1a4ba3fed3efef47b5f5650f246e9d14b39dc3a35195dd638c03d"
SERIES_PREFIX_SHA256 = "af13b1c2590219cca7e11cd5bddde30ed2464d79292344ed355d6fd3410f2003"
SERIES_239_SHA256 = "1cf9d873f5418c9928a845196c9b4a3f3fe5009f9ab5352cf67e6c2119dff620"
PATCH_SHA256 = "8240dcbf0fc9563a4cae6b6405278553ab4689a6760c919421448d65d8ee8575"

HUNKS = [
    "@@ -11,6 +11,9 @@",
    "@@ -463,11 +463,26 @@",
    "@@ -46,6 +46,7 @@",
    "@@ -292,6 +293,10 @@",
    "@@ -309,6 +314,12 @@",
    "@@ -1163,6 +1174,42 @@",
    "@@ -1942,6 +1989,7 @@",
    "@@ -2019,7 +2067,8 @@",
    "@@ -2075,6 +2124,7 @@",
    "@@ -2085,6 +2135,16 @@",
    "@@ -2109,6 +2169,9 @@",
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
    check(PATCH.is_file(), "0523 patch exists", str(PATCH))
    check(sha256(PATCH) == PATCH_SHA256, "0523 bytes", sha256(PATCH))

    diff = PATCH.read_text(encoding="utf-8")
    for hunk in HUNKS:
        check(hunk in diff, "hunk header", hunk)

    added = [line[1:] for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]

    check(any("int (*set_rate)(void *, uint32_t baud);" in line for line in added),
          "the transport ops carry a set_rate hook")
    check(any("e=bt_ops.set_rate?bt_ops.set_rate(bt_ops.context,speed):EINVAL;" in line
              for line in added),
          "TIOCSETA goes through the hook before it reports success")
    check(any("bt_sk_speed=speed;" in line for line in added),
          "the transport adopts the reclocked speed")
    check(any("#include <kern/locks.h>" in line for line in added),
          "the board takes a kernel mutex")
    check(any("static LCK_MTX_DECLARE(k60_rate_lock, &k60_rate_grp);" in line
              for line in added),
          "the engine lock is statically declared")
    check(any("if (!k60.powered || !k60.ready) return ENODEV;" in line for line in added),
          "the link must be powered before it is reclocked")
    check(any("k60.rate_request = baud;" in line for line in added),
          "the request is handed to the worker")
    check(any('msleep(&k60.rate_done, &k60_rate_lock, PZERO, "k60bt-rate", &timeout);' in line
              for line in added),
          "the client blocks on the worker result with a timeout")
    check(any("k60.rate_error = k60_uart_speed(NULL, requested);" in line for line in added),
          "the worker reclocks through k60_uart_speed")
    check(any("wakeup(&k60.rate_done);" in line for line in added),
          "the worker wakes the waiting client")
    check(any(".set_rate = k60_transport_set_rate };" in line for line in added),
          "the board registers the hook")
    check(any("k60.ready = k60.powered;" in line for line in added),
          "readiness is published after the boot ladder")
    check(any("k60.ready = false;" in line for line in added),
          "power off drops readiness")
    check(not any("3200000u" in line for line in added),
          "0523 does not touch the published transport speed")
    check("bsd/dev/qbt/qbt_transport.h" in diff and
          "bsd/dev/qbt/qbt_transport.c" in diff and
          "bsd/dev/qbt_k60.c" in diff,
          "0523 touches the transport header, transport and board backend")
    check("bsd/kern/kern_exec.c" not in diff and "MiniBluetooth.cpp" not in diff,
          "0523 touches nothing else")

    lines = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    check(len(lines) == SERIES_COUNT, "series count", str(len(lines)))
    check(lines[SERIES_COUNT - 1] == "0523-k60-bt-transport-set-rate.patch",
          "line 241 is 0523", lines[SERIES_COUNT - 1])
    series_sha = hashlib.sha256(
        ("\n".join(lines) + "\n").encode()).hexdigest()
    check(series_sha == SERIES_SHA256, "241-line series sha256", series_sha)
    prefix_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_PREFIX_COUNT]) + "\n").encode()).hexdigest()
    check(prefix_sha == SERIES_PREFIX_SHA256, "240-line 0500..0520 prefix sha256",
          prefix_sha)
    short_sha = hashlib.sha256(
        ("\n".join(lines[:239]) + "\n").encode()).hexdigest()
    check(short_sha == SERIES_239_SHA256, "239-line 0500..0519 prefix sha256", short_sha)
    check(sha256(PATCHES / "0520-k60-bt-uart-control-alias.patch") ==
          "15d553964af34bcaf2555a90b1f73548cdabcd45634f14e1cfc20ee3a663d61a",
          "0520 bytes are unchanged")
    check(sha256(PATCHES / "0519-k60-bt-userspace-power-nodes.patch") ==
          "7e547a20a52cdf446b0e38ec376a64057cf4c542c188e25bd1e36df9ac8a63d8",
          "0519 bytes are unchanged")

    print(f"TESTS OK {checks} cases / 0 failure")


if __name__ == "__main__":
    main()
