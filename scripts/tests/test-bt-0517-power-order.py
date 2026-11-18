#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Host-only checks for the 0517 official Bluetooth power-order candidate.

The test binds the patch bytes and the series tail.  It does not boot a
device, touch the controller or prove the UART/GENI sequence at runtime.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches" / "xnu"
SERIES = PATCHES / "series"
PATCH = PATCHES / "0517-k60-bt-power-order.patch"

PATCH_0516 = "0516-k60-bt-qbt-uart-clock.patch"
PATCH_0517 = "0517-k60-bt-power-order.patch"
PATCH_0518 = "0518-k60-bt-gic-intid.patch"
SERIES_PREFIX_COUNT = 236
SERIES_PREFIX_SHA256 = "e7de39278e0eb0da1c5a5036e0645466885678eefdf57835e279f0bef2717db2"
SERIES_COUNT = 237
SERIES_SHA256 = "3339e34f664d8eee48ab366ec98bffd00018aafe82821c1b7f9b5eecd8dcbcba"
PATCH_SHA256 = "ebd0fe356a28281169b6d6aebe177020672ccbe4237a8b78735a4429ec7f5cbe"

HUNKS = [
    "@@ -258,8 +258,8 @@",
    "@@ -1878,28 +1878,23 @@",
    "@@ -1915,6 +1910,11 @@",
]

MARKERS = [
    "k60_uart_pins_idle();",
    "k60_gpio_output(K60_BT_EN_GPIO, false, K60_TLMM_PULL_DOWN, K60_TLMM_DRIVE_2MA);",
    "IOSleep(K60_BT_EN_LOW_MS);",
    "k60.powered = true;",
    "if (!k60_pin_input(K60_WLAN_EN_GPIO))",
    "IOSleep(K60_WLAN_OFF_DISCHARGE_MS);",
    "k60_gpio_input(K60_BT_SW_CTRL_GPIO, K60_TLMM_PULL_NONE, K60_TLMM_DRIVE_2MA);",
    "e = k60_serial_clock(true);",
    "e = k60_stop_engine();",
    "e = k60_prepare_engine();",
    "k60.wake_irq = true;",
    "k60_xo_pulse();",
    "k60_gpio_output(K60_BT_EN_GPIO, true, K60_TLMM_PULL_DOWN, K60_TLMM_DRIVE_2MA);",
    "k60_xo_release();",
    "IOSleep(K60_BT_EN_HIGH_MS);",
    "k60_uart_pins_active();",
    "e = qbt_geni_start(&k60.geni);",
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
    """Return the new-side text of all hunks, in file order."""
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
    """Return (old_start, old_count, new_start, new_count) for every hunk."""
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
    check(PATCH.is_file(), "0517 patch exists", str(PATCH))
    check(SERIES.is_file(), "series exists", str(SERIES))
    check(sha256(PATCH) == PATCH_SHA256, "0517 patch sha256", sha256(PATCH))

    diff = PATCH.read_text(encoding="utf-8")
    check("\r" not in diff, "0517 patch uses LF endings")
    check(diff.endswith("\n"), "0517 patch ends with a newline")
    check(diff.count("diff --git ") == 1, "0517 patch changes one file")
    check("diff --git a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c" in diff,
          "0517 patch targets bsd/dev/qbt_k60.c")
    check([line for line in diff.splitlines() if line.startswith("@@")] == HUNKS,
          "0517 hunk headers", str([line for line in diff.splitlines() if line.startswith("@@")]))

    rows = hunk_counts(diff)
    check(rows == [(258, 8, 258, 8), (1878, 28, 1878, 23), (1915, 6, 1910, 11)],
          "0517 hunk ranges", str(rows))

    side = new_side(diff)
    check(side.count("k60_uart_pins_idle();") == 1, "one pins-idle call")
    check(side.count("k60_uart_pins_active();") == 1, "one pins-active call")
    check(side.count("k60_xo_pulse();") == 1, "one XO pulse")
    check(side.count("k60_xo_release();") == 1, "one XO release")
    check(side.count("k60_gpio_output(K60_BT_EN_GPIO, false,") == 1,
          "one BT_EN low call")
    check(side.count("k60_gpio_output(K60_BT_EN_GPIO, true,") == 1,
          "one BT_EN high call")

    positions = []
    for marker in MARKERS:
        check(side.count(marker) == 1, "one occurrence", marker)
        positions.append(side.index(marker))
    check(all(a < b for a, b in zip(positions, positions[1:])),
          "official power order", str(positions))

    check("#define K60_BT_EN_LOW_MS            100u" in side,
          "BT_EN low is 100 ms")
    check("#define K60_BT_EN_HIGH_MS           60u" in side,
          "BT_EN high wait is 60 ms")
    check("#define K60_BT_EN_LOW_MS            50u" in diff,
          "old 50 ms low hold is removed")
    check("#define K60_BT_EN_HIGH_MS           50u" in diff,
          "old 50 ms high wait is removed")
    check("-    k60_uart_pins_active();" in diff,
          "old early pins-active call is removed")
    check("-    if (k60_pin_input(K60_WLAN_EN_GPIO)) {" in diff,
          "old non-negated WLAN check is removed")
    check(side.index("k60_uart_pins_active();") >
          side.index("IOSleep(K60_BT_EN_HIGH_MS);"),
          "pins become active after the 60 ms wait")
    check(side.index("k60_xo_pulse();") > side.index("k60.wake_irq = true;"),
          "BT_EN high follows the wake IRQ attach block")
    check(side.index("k60_uart_pins_active();") >
          side.index("k60.wake_irq = true;"),
          "pins become active after the wake IRQ attach block")
    check("k60_bt_power_off" not in diff,
          "power-off sequence is not part of 0517")

    lines = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    check(len(lines) >= SERIES_COUNT, "series count", str(len(lines)))
    check(lines[SERIES_PREFIX_COUNT - 1] == PATCH_0516,
          "line 236 is 0516", lines[SERIES_PREFIX_COUNT - 1])
    check(lines[SERIES_COUNT - 1] == PATCH_0517,
          "line 237 is 0517", lines[SERIES_COUNT - 1])
    tail_ok = all(line.startswith(("0518-", "0519-", "0520-"))
                  for line in lines[SERIES_COUNT:])
    check(tail_ok, "candidate tail is 0517 optionally followed by later patches")
    prefix_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_PREFIX_COUNT]) + "\n").encode()).hexdigest()
    check(prefix_sha == SERIES_PREFIX_SHA256, "236-line 0516 prefix sha256", prefix_sha)
    candidate_sha = hashlib.sha256(
        ("\n".join(lines[:SERIES_COUNT]) + "\n").encode()).hexdigest()
    check(candidate_sha == SERIES_SHA256, "237-line 0517 series sha256", candidate_sha)
    check(sha256(PATCHES / PATCH_0516) ==
          "0134a31bedb65fe6669a7ce7745bc5b9fcb6a7cd44ac66f96f3f604bb01ac6c8",
          "0516 bytes are unchanged")

    print(f"TESTS OK {checks} cases / 0 failure")


if __name__ == "__main__":
    main()
