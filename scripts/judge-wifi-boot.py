#!/usr/bin/env python3
"""Classify one K60 USB console log into the four BOOT-DEATH-BISECT verdicts.

Why this exists: docs/research/wifi/BOOT-DEATH-BISECT.md section 7 defines four
flight criteria (C1-C4) that decide, within seconds of a capture finishing,
whether the next wifi experiment keeps bisecting the driver or switches to the
kernel-size direction.  Judging four criteria by eye across a ~230 KB console
log is error-prone exactly when it matters most (the wifi-20261116a2 control
flight), so this tool reads the log and prints the verdict plus the next step.

Verdicts:
  alive        console has userspace markers (SpringBoard) and no wifi failure
  driver-dead  console exists, the wifi worker printed and then the log stops
               (or its failure string is near the end)
  silent       zero bytes, or only UEFI/pre-console noise: the death happened
               before k60_usblog_start() ever printed (BOOT-DEATH-BISECT.md
               section 5: DarwinBoot/UEFI or early XNU)
  unknown      console exists but shows neither userspace nor a wifi verdict

Usage:
    python3 scripts/judge-wifi-boot.py <console.log> [--bytes N]
    python3 scripts/judge-wifi-boot.py <capture-dir>        # uses capture.json

Exit codes: 0 alive, 1 driver-dead, 2 silent, 3 unknown, 4 usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# Console markers that prove userspace was reached.  Every healthy capture in
# evidence/usblog-20261115-* carries all of them; a wifi-driver-dead boot shows
# none because the console dies (or the capture ends) before launchd.
USERSPACE_MARKERS = (
    "SpringBoard",
    "K60XPC compat=",
    "launchd",
)

# Strings the PongWifi driver itself prints (PongWifiPlatform.cpp log()/fail(),
# PongWifiNet.cpp, plus the worker failure strings from the 0011 stage gate).
# The evidence tree has never contained a PongWifi line yet, so this list is the
# contract for what a future capture must match; keep it in sync with the
# driver's log()/fail() call sites.
WIFI_LINE_RE = re.compile(
    r"PongWifi:|Pong MHI|wifi-net:|PongWifi\[\d\]|"
    r"console never came up|UFS prerequisites absent|"
    r"network event setup failed|Apps SMMU lease"
)

# The worker failure strings that end a wifi bring-up (fail() call sites in
# PongWifiPlatform.cpp worker()); if one of these is the last wifi line the
# verdict is driver-dead rather than unknown.
WIFI_FAILURE_RE = re.compile(
    r"console never came up|UFS prerequisites absent|"
    r"network event setup failed|Apps SMMU lease|"
    r"cold link failed|link never came up|PCIe link training failed"
)

# Stage-gate marker: proves the 0011 stage mechanism itself ran (C4).
STAGE_HELD_RE = re.compile(r"PongWifi: stage \d+ \([^)]*\) held back by k60_wifi_stage")

# Lines that appear before the XNU console takes over.  A log made only of
# these (plus UEFI chatter) means the kernel never printed: the silent class.
PRE_CONSOLE_RE = re.compile(
    r"fastboot|Sending 'boot|OKAY|Finished\. Total time|"
    r"Downloading|BootLinux|UEFI|UniXNU launcher|DarwinBoot",
    re.IGNORECASE,
)

# Number of bytes a driver-dead tail window covers; the failure string must sit
# within this window of the end of the log to count as the death point.
TAIL_WINDOW = 4000


def load_text(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    return data


def classify(data: bytes, declared_bytes: int | None) -> tuple[str, list[str]]:
    """Return (verdict, notes).  data may be empty."""
    notes: list[str] = []
    size = declared_bytes if declared_bytes is not None else len(data)
    if size == 0:
        return "silent", ["console.log is 0 bytes: nothing before the death printed"]

    text = data.decode("utf-8", "replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "silent", ["console.log carries no printable line"]

    userspace = [m for m in USERSPACE_MARKERS if m in text]
    wifi_lines = [(i, ln) for i, ln in enumerate(lines) if WIFI_LINE_RE.search(ln)]
    stage_held = [ln for ln in lines if STAGE_HELD_RE.search(ln)]

    if userspace:
        notes.append("userspace markers: " + ", ".join(userspace[:4]))
        if stage_held:
            notes.append(f"stage gate held {len(stage_held)} stage(s); gate mechanism works (C4)")
        if wifi_lines:
            last = wifi_lines[-1][1].strip()
            notes.append(f"last wifi line: {last[:160]}")
        # A userspace boot with a wifi failure string still means the kernel
        # survived the driver; the driver work continues from its last line.
        if wifi_lines and WIFI_FAILURE_RE.search(wifi_lines[-1][1]):
            return "alive", notes + ["wifi worker failed but the kernel reached userspace"]
        return "alive", notes

    if wifi_lines:
        last_no, last = wifi_lines[-1]
        tail_start = max(0, len(lines) - max(1, TAIL_WINDOW // 80))
        near_end = last_no >= tail_start
        notes.append(f"last wifi line ({last_no + 1}/{len(lines)}): {last.strip()[:160]}")
        if WIFI_FAILURE_RE.search(last):
            notes.append("the log ends in a wifi worker failure")
            return "driver-dead", notes
        if near_end:
            notes.append("no userspace marker after the wifi line")
            return "driver-dead", notes
        return "unknown", notes + [
            "wifi lines exist but neither userspace nor an end-of-log failure follows",
        ]

    # No wifi line at all.  If every line looks like pre-console noise, the
    # death happened before k60_usblog_start(): silent.
    noisy = sum(1 for ln in lines if PRE_CONSOLE_RE.search(ln))
    if noisy == len(lines):
        return "silent", ["only pre-console/fastboot noise: the kernel never printed"]
    return "unknown", [
        f"console has {len(lines)} lines but no userspace and no PongWifi marker",
        "check whether this image carries the wifi driver at all (PongWifi strings)",
    ]


def verdict_exit(verdict: str) -> int:
    return {"alive": 0, "driver-dead": 1, "silent": 2, "unknown": 3}[verdict]


def next_step(verdict: str, notes: list[str]) -> list[str]:
    if verdict == "alive":
        return [
            "next: keep bisecting the driver with k60_wifi_stage (1..10);",
            "      stage N held = the fault sits in stage N+1 (BOOT-DEATH-BISECT.md section 7 C3/C4)",
        ]
    if verdict == "driver-dead":
        return [
            "next: the death point is inside the wifi worker; instrument around",
            "      the last printed line before the next flight (section 7 C3)",
        ]
    if verdict == "silent":
        return [
            "next: switch to the size/residency direction (section 7 C2):",
            "      a2 (65.9 MB, pong_wifi=0) vs mhi3/mhi4 (65.9 MB, pong_wifi=1) vs",
            "      z0/t0c (54.2/54.8 MB): if a2 is also silent the driver is exonerated",
            "      and DarwinBoot window/pool maths (DarwinBoot.c:558,607) becomes the suspect",
        ]
    return [
        "next: verdict inconclusive; compare the capture with the previous flight",
        "      and re-run with --bytes if capture.json disagrees with the file size",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=pathlib.Path,
                    help="console.log path, or a capture directory containing capture.json")
    ap.add_argument("--bytes", type=int, default=None,
                    help="trust this size instead of the file size (use 0 for a capture.json-declared empty log)")
    args = ap.parse_args()

    log = args.log
    declared: int | None = None
    if log.is_dir():
        cap = log / "capture.json"
        log_file = log / "console.log"
        if cap.is_file():
            try:
                cap_data = json.loads(cap.read_text(encoding="utf-8-sig"))
                declared = int(cap_data.get("bytes", -1))
                if declared < 0:
                    declared = None
            except (json.JSONDecodeError, OSError):
                print("wifi-boot-judge: capture.json is unreadable; falling back to the log file")
        if not log_file.is_file():
            raise SystemExit(f"wifi-boot-judge: {log} has no console.log")
        log = log_file
    if not log.is_file():
        raise SystemExit(f"wifi-boot-judge: no such log: {args.log}")

    data = load_text(log)
    verdict, notes = classify(data, declared)
    print(f"wifi-boot-judge: {verdict} ({log.name}, {len(data)} bytes on disk"
          + (f", capture.json declares {declared}" if declared is not None else "") + ")")
    for n in notes:
        print("  -", n)
    for line in next_step(verdict, notes):
        print(line)
    return verdict_exit(verdict)


if __name__ == "__main__":
    sys.exit(main())
