#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only checks for the 0518 GIC INTID candidate.

The device tree gives the GIC SPI number (587 for QUPV3_2 SE20 and 208 for
the TLMM summary).  armcpu_spi_attach/mask and the GICD enable registers take
the INTID, so every SPI must be shifted by 32.  The same convention is used
by the UFS (265 + 32) and PCIe (32 + 140) callers, and ArmCpu.cpp rejects
INTIDs below 32.

This test binds the patch bytes and the series tail.  It does not boot a
device, touch the controller or prove the interrupt routing at runtime.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches" / "xnu"
SERIES = PATCHES / "series"
PATCH = PATCHES / "0518-k60-bt-gic-intid.patch"

PATCH_0516 = "0516-k60-bt-qbt-uart-clock.patch"
PATCH_0517 = "0517-k60-bt-power-order.patch"
PATCH_0518 = "0518-k60-bt-gic-intid.patch"
SERIES_PREFIX_COUNT = 237
SERIES_PREFIX_SHA256 = "3339e34f664d8eee48ab366ec98bffd00018aafe82821c1b7f9b5eecd8dcbcba"
SERIES_COUNT = 238
SERIES_SHA256 = "4a39a8d2fddf0da93dbcab18a2302c69bab8f34955d56e9172c1a395e8b12e11"
PATCH_SHA256 = "c1e2cb96ac79b26089e4a495741165d800ee8e730b0a460ab2e476853809e13f"

HUNKS = [
    "@@ -86,8 +86,11 @@",
    "@@ -111,6 +114,7 @@",
    "@@ -910,8 +914,8 @@",
    "@@ -1900,13 +1904,13 @@",
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


def new_side(diff: str) -> str:
    out: list[str] = []
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith(" "):
            out.append(line[1:])
    return "\n".join(out)


def hunk_counts(diff: str) -> list[tuple[int, int, int, int]]:
    rows: list[tuple[int, int, int, int]] = []
    current: list[int] | None = None
    old_seen = 0
    new_seen = 0
    for line in diff.splitlines():
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            if current is not None:
                check((old_seen, new_seen) == (current[1], current[3]),
                      "hunk line counts", f"{current}: {old_seen}/{new_seen}")
            current = [int(m.group(1)), int(m.group(2) or "1"),
                       int(m.group(3)), int(m.group(4) or "1")]
            rows.append(tuple(current))
            old_seen = 0
            new_seen = 0
            continue
        if current is None:
            continue
        if line.startswith("-") and not line.startswith("---"):
            old_seen += 1
        elif line.startswith("+") and not line.startswith("+++"):
            new_seen += 1
        elif line.startswith(" "):
            old_seen += 1
            new_seen += 1
    if current is not None:
        check((old_seen, new_seen) == (current[1], current[3]),
              "hunk line counts", f"{current}: {old_seen}/{new_seen}")
    return rows


def main() -> None:
    check(PATCH.is_file(), "0518 patch exists", str(PATCH))
    check(SERIES.is_file(), "series exists", str(SERIES))
    check(sha256(PATCH) == PATCH_SHA256, "0518 patch sha256", sha256(PATCH))

    diff = PATCH.read_text(encoding="utf-8")
    check("\r" not in diff, "0518 patch uses LF endings")
    check(diff.endswith("\n"), "0518 patch ends with a newline")
    check(diff.count("diff --git ") == 1, "0518 patch changes one file")
    check("diff --git a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c" in diff,
          "0518 patch targets bsd/dev/qbt_k60.c")
    check([line for line in diff.splitlines() if line.startswith("@@")] == HUNKS,
          "0518 hunk headers", str([line for line in diff.splitlines() if line.startswith("@@")]))

    rows = hunk_counts(diff)
    check(rows == [(86, 8, 86, 11), (111, 6, 114, 7),
                   (910, 8, 914, 8), (1900, 13, 1904, 13)],
          "0518 hunk ranges", str(rows))

    side = new_side(diff)
    check(side.count("#define K60_BT_UART_GIC_SPI         587u") == 1,
          "UART DT SPI number unchanged")
    check(side.count("#define K60_BT_UART_GIC_INTID       (32u + K60_BT_UART_GIC_SPI)") == 1,
          "UART INTID is SPI + 32")
    check(side.count("#define K60_TLMM_GIC_SPI            208u") == 1,
          "TLMM DT SPI number unchanged")
    check(side.count("#define K60_TLMM_GIC_INTID          (32u + K60_TLMM_GIC_SPI)") == 1,
          "TLMM INTID is SPI + 32")

    check(side.count("k60_gic_mask(K60_BT_UART_GIC_INTID, masked);") == 1,
          "GICD mask uses the UART INTID")
    check(side.count("armcpu_spi_mask(K60_BT_UART_GIC_INTID, masked)") == 1,
          "ArmCpu mask uses the UART INTID")
    check(side.count("armcpu_spi_attach(K60_BT_UART_GIC_INTID, false, k60_uart_irq") == 1,
          "UART handler attaches to the INTID")
    check(side.count("armcpu_spi_attach(K60_TLMM_GIC_INTID, false, k60_tlmm_irq") == 1,
          "TLMM handler attaches to the INTID")

    added = [line[1:] for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    check(not any("k60_gic_mask(K60_BT_UART_GIC_SPI" in line for line in added),
          "no raw UART SPI reaches the GICD mask")
    check(not any("armcpu_spi_mask(K60_BT_UART_GIC_SPI" in line for line in added),
          "no raw UART SPI reaches the ArmCpu mask")
    check(not any("armcpu_spi_attach(K60_BT_UART_GIC_SPI" in line for line in added),
          "no raw UART SPI reaches the UART attach")
    check(not any("armcpu_spi_attach(K60_TLMM_GIC_SPI" in line for line in added),
          "no raw TLMM SPI reaches the TLMM attach")
    check("-        k60_gic_mask(K60_BT_UART_GIC_SPI, masked);" in diff,
          "old raw UART mask is removed")
    check("-        e = armcpu_spi_attach(K60_BT_UART_GIC_SPI," in diff,
          "old raw UART attach is removed")
    check("-        e = armcpu_spi_attach(K60_TLMM_GIC_SPI," in diff,
          "old raw TLMM attach is removed")

    lines = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    check(len(lines) == SERIES_COUNT, "series count", str(len(lines)))
    check(lines[SERIES_PREFIX_COUNT - 1] == PATCH_0517,
          "line 237 is 0517", lines[SERIES_PREFIX_COUNT - 1])
    check(lines[-1] == PATCH_0518, "series ends with 0518", lines[-1])
    prefix_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_PREFIX_COUNT]) + "\n").encode()).hexdigest()
    check(prefix_sha == SERIES_PREFIX_SHA256, "237-line 0516+0517 prefix sha256", prefix_sha)
    full_sha = hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    check(full_sha == SERIES_SHA256, "238-line series sha256", full_sha)
    check(sha256(PATCHES / PATCH_0516) ==
          "0134a31bedb65fe6669a7ce7745bc5b9fcb6a7cd44ac66f96f3f604bb01ac6c8",
          "0516 bytes are unchanged")
    check(sha256(PATCHES / PATCH_0517) ==
          "ebd0fe356a28281169b6d6aebe177020672ccbe4237a8b78735a4429ec7f5cbe",
          "0517 bytes are unchanged")

    print(f"TESTS OK {checks} cases / 0 failure")


if __name__ == "__main__":
    main()
