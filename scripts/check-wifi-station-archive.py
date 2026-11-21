#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Prove that a 27 station archive meets the contract the driver links against.

The driver archive records _nw_wifi_power and _nw_wifi_scan_frequencies as
undefined; a station archive that does not define them links only through
scratch definitions. Four separate things are checked together because each
one alone passed in a failure we hit:

  1. every member is an arm64e Mach-O object (cputype 0x0100000C, cpusubtype
     low 24 bits 2), so -force_load on the arm64e kernel keeps the members;
  2. the archive defines both station APIs instead of referencing them;
  3. abi/nw_abi.stamp next to the archive says ie_bytes=2048 and its
     header_sha256 matches the abi/nw_abi.h beside it. The builder only
     checked ie_bytes, so a regenerated header could describe objects that
     were compiled against the previous one;
  4. the archive does not define the five scratch stubs that let a historical
     link succeed (P-283). A stub is a property of content, not a filename.

    python3 scripts/check-wifi-station-archive.py <archive> [--ar <ar>] [--nm <nm>]

Exit 0 when all four hold, 1 when the archive breaks the contract, 2 when an
input or a tool is missing. An archive nobody could read is not a pass. An
absent archive is exit 2 with a note that it has not been built, never a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
REQUIRED_APIS = ("_nw_wifi_power", "_nw_wifi_scan_frequencies")
SCRATCH_STUBS = ("_psci_smp_init", "_psci_smp_start_cpu", "_psci_smp_cpu_running",
                 "_psci_smp_cpu_off", "_pong_cpu_startup_finished")
EXPECTED_IE_BYTES = 2048


def parse_member_header(data: bytes) -> tuple[int, int]:
    """Return (cputype, cpusubtype) from a 64-bit Mach-O object header."""
    if len(data) < 12:
        raise ValueError("member is shorter than a Mach-O header")
    magic, cputype, cpusubtype = struct.unpack_from("<III", data, 0)
    if magic != MH_MAGIC_64:
        raise ValueError(f"member is not a 64-bit Mach-O object (magic 0x{magic:08x})")
    return cputype, cpusubtype


def is_arm64e(cputype: int, cpusubtype: int) -> bool:
    return cputype == CPU_TYPE_ARM64 and (cpusubtype & 0x00FFFFFF) == CPU_SUBTYPE_ARM64E


def parse_nm(text: str) -> set[str]:
    """Collect defined symbol names from posix-format nm output."""
    defined: set[str] = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2 or len(fields[1]) != 1:
            continue
        name, kind = fields[0], fields[1]
        if kind == "U":
            continue
        defined.add(name)
    return defined


def parse_stamp(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def run(argv: list[str], binary: bool = False):
    try:
        result = subprocess.run(argv, capture_output=True, text=not binary)
    except FileNotFoundError:
        raise SystemExit(2)
    if result.returncode != 0:
        detail = result.stderr
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise SystemExit(2 if not detail.strip() else 1)
    return result.stdout


def check(archive: Path, ar: str, nm: str) -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []
    members = [line.strip() for line in run([ar, "t", str(archive)]).splitlines() if line.strip()]
    if not members:
        return [(False, "members: the archive is empty")]
    wrong: list[str] = []
    for member in members:
        header = run([ar, "p", str(archive), member], binary=True)
        try:
            cputype, cpusubtype = parse_member_header(header)
        except ValueError as error:
            wrong.append(f"{member} ({error})")
            continue
        if not is_arm64e(cputype, cpusubtype):
            wrong.append(f"{member} is not arm64e (cputype 0x{cputype:08x}, cpusubtype 0x{cpusubtype:08x})")
    results.append((not wrong, "members: " + (", ".join(wrong) if wrong else f"{len(members)} arm64e")))
    defined = parse_nm(run([nm, "--defined-only", "--format=posix", str(archive)]))
    missing = [api for api in REQUIRED_APIS if api not in defined and api.lstrip("_") not in defined]
    results.append((not missing, "station API: " + (", ".join(missing) if missing else ", ".join(REQUIRED_APIS))))
    stubs = [stub for stub in SCRATCH_STUBS if stub in defined]
    if stubs:
        results.append((False, "stubs: " + ", ".join(stubs)))
        return results
    results.append((True, "stubs: no scratch stub symbols"))
    stamp = archive.parent / "abi" / "nw_abi.stamp"
    header = archive.parent / "abi" / "nw_abi.h"
    if not stamp.is_file():
        raise FileNotFoundError(stamp)
    values = parse_stamp(stamp.read_text(encoding="utf-8"))
    if values.get("ie_bytes") != str(EXPECTED_IE_BYTES):
        results.append((False, f"stamp: ie_bytes={values.get('ie_bytes')}, expected {EXPECTED_IE_BYTES}"))
        return results
    expected = values.get("header_sha256", "")
    if not header.is_file():
        raise FileNotFoundError(header)
    actual = hashlib.sha256(header.read_bytes()).hexdigest()
    results.append((expected == actual, f"stamp: header_sha256 {actual}" if expected == actual else f"stamp: header_sha256 {actual} does not match {expected}"))
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the 27 station archive contract.")
    parser.add_argument("archive", help="libPongAth11k.a to inspect")
    parser.add_argument("--ar", default=os.environ.get("K60_AR", "llvm-ar"))
    parser.add_argument("--nm", default=os.environ.get("K60_NM", "llvm-nm"))
    args = parser.parse_args(argv)
    archive = Path(args.archive)
    if not archive.is_file():
        print(f"note: {archive} is absent; the 27 station archive has not been built", file=sys.stderr)
        return 2
    try:
        results = check(archive, args.ar, args.nm)
    except FileNotFoundError as missing:
        print(f"FAIL stamp: {missing} is missing")
        return 2
    except SystemExit as exit_code:
        print(f"FAIL read: {archive} could not be read ({exit_code})", file=sys.stderr)
        return 2
    ok = True
    for passed, line in results:
        ok = ok and passed
        print(("PASS " if passed else "FAIL ") + line)
    if not ok:
        print("station archive contract: FAIL", file=sys.stderr)
        return 1
    print(f"station archive contract: PASS ({archive.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
