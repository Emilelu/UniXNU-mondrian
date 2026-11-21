#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Recompute the B4 27 kernel-export / archive-undefined comparison.

B4 asks whether the 12377 kernel exports what the Wi-Fi driver links against.
The answer is not a symbol-presence spot check: take the com.apple.kernel
exports from the 27 kernel, then classify every undefined symbol in the driver
archive and the station archive as resolved by the kernel, by the same archive,
by the other archive, by the two station APIs, or absent.

The numbers and a full output snapshot are recorded in
docs/research/wifi/evidence/ios27-b4-exports.txt. Run this after a new kernel
or archive is produced; a changed count is a changed answer, not a green run.

    python3 scripts/check-wifi-b4-exports.py \
      --kernel /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho \
      --driver /opt/k60/trees/k60build/wifi/teardown27g/libPongWifiNative.a \
      --station /opt/k60/trees/k60build/wifi/ath11k-abi27e/libPongAth11k.a \
      --nm /usr/bin/llvm-nm-18
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

STATION_APIS = {"_nw_wifi_power", "_nw_wifi_scan_frequencies"}
ORDER = ("kernel", "same-archive", "other-archive", "station-API", "absent")


def tool_argv(nm: str, *args: str) -> list[str]:
    if nm.endswith(".py"):
        return [sys.executable, nm, *args]
    return [nm, *args]


def run(nm: str, *args: str) -> list[str]:
    result = subprocess.run(tool_argv(nm, *args), capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"nm failed: {nm} {' '.join(args)}\n{result.stderr}")
    return result.stdout.splitlines()


def kernel_exports(nm: str, path: Path) -> set[str]:
    current = None
    exports: set[str] = set()
    for line in run(nm, "-g", "--format=posix", str(path)):
        if line.startswith("Symbols for "):
            current = line[len("Symbols for "):].strip().rstrip(":").strip()
            continue
        if current != "com.apple.kernel":
            continue
        fields = line.split()
        if len(fields) >= 2 and fields[1] != "U":
            exports.add(fields[0])
    return exports


def archive_symbols(nm: str, path: Path, undefined: bool) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    args = ["-A", "--format=posix", str(path)]
    if undefined:
        args.insert(0, "-u")
    for line in run(nm, *args):
        match = re.match(r"^(.*?)\[([^\]]+)\]: (\S+) ([A-Za-z?])", line)
        if not match:
            continue
        _, member, symbol, kind = match.groups()
        if undefined and kind != "U":
            continue
        if not undefined and kind == "U":
            continue
        out[symbol].add(member)
    return out


def classify(symbol: str, own: dict[str, set[str]], other: dict[str, set[str]],
             kernel: set[str]) -> str:
    if symbol in kernel:
        return "kernel"
    if symbol in own:
        return "same-archive"
    if symbol in other:
        return "other-archive"
    if symbol in STATION_APIS:
        return "station-API"
    return "absent"


def report(label: str, undefined: dict[str, set[str]], own: dict[str, set[str]],
           other: dict[str, set[str]], kernel: set[str]) -> tuple[int, list[str]]:
    counts: dict[str, int] = defaultdict(int)
    missing: list[str] = []
    for symbol in undefined:
        status = classify(symbol, own, other, kernel)
        counts[status] += 1
        if status in ("station-API", "absent"):
            missing.append(symbol)
    summary = ", ".join(f"{kind}={counts.get(kind, 0)}" for kind in ORDER)
    print(f"{label} undefined: {len(undefined)} ({summary})")
    print(f"{label} resolved: {len(undefined) - len(missing)}")
    if missing:
        print(f"{label} missing: {', '.join(sorted(missing))}")
    return len(undefined) - len(missing), missing


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Recompute the B4 27 link comparison.")
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--station", required=True, type=Path)
    parser.add_argument("--nm", default="/usr/bin/llvm-nm-18")
    args = parser.parse_args(argv)
    for path in (args.kernel, args.driver, args.station):
        if not path.is_file():
            print(f"missing input: {path}")
            return 2
    try:
        kernel = kernel_exports(args.nm, args.kernel)
        driver_def = archive_symbols(args.nm, args.driver, False)
        driver_und = archive_symbols(args.nm, args.driver, True)
        station_def = archive_symbols(args.nm, args.station, False)
        station_und = archive_symbols(args.nm, args.station, True)
    except (OSError, SystemExit) as error:
        print(error)
        return 2
    print(f"kernel com.apple.kernel exports: {len(kernel)}")
    driver_resolved, driver_missing = report("driver", driver_und, driver_def, station_def, kernel)
    station_resolved, station_missing = report("station", station_und, station_def, driver_def, kernel)
    print(
        "B4: "
        f"{len(kernel)} exports; {len(driver_und)} driver undefined, {driver_resolved} resolved, "
        f"{len(driver_missing)} missing; {len(station_und)} station undefined, "
        f"{station_resolved} resolved, {len(station_missing)} missing"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
