#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Refuse a 27 kernel link whose inputs are the wrong architecture or undeclared.

The 27 kernel is arm64e. Two failures look like a successful build and are
only visible in the link inputs: ld drops an archive built for arm64 with a
warning and counts zero of its symbols, and a scratch archive with hand-written
definitions makes an image link that has no driver behind it. Both are already
written down in the link record the kernel build leaves beside the object tree,
so the check needs no build of its own:

  1. arch        every archive member has the kernel s cputype and cpusubtype
                 (arm64e: 0x0100000C and 0x2); an archive that does not exist
                 is a refusal, not a skip;
  2. provenance  every archive is inside a declared root, or is listed with
                 its sha256 in --declared, and none matches --forbid. A
                 scratch stub fails both halves of that sentence.

    python3 scripts/check-wifi27-link-inputs.py --link-record <file> \\
        --allow-root /tmp/<tree> --allow-root /opt/k60/trees/k60build/wifi \\
        [--kernel-arch arm64e] [--declared <file>] [--ar <llvm-ar>]

Exit 0 when both assertions hold, 1 when an input breaks one of them, 2 when
the record or a tool cannot be read. This is the lane preflight entry: one
command runs both assertions and the exit status is their conjunction. It is
deliberately not an entry in docs/engineering/IOS27-FLIGHT-BLOCKERS.toml:
that ledger decides whether a whole image may fly, and a Wi-Fi input must not
refuse a stage-0 image that carries no Wi-Fi archive at all.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
DEFAULT_FORBID = r"(^|/)libStub|(^|/)stub[0-9]|/scratch/"


def parse_member_header(data: bytes) -> tuple[int, int]:
    if len(data) < 12:
        raise ValueError("member is shorter than a Mach-O header")
    magic, cputype, cpusubtype = struct.unpack_from("<III", data, 0)
    if magic != MH_MAGIC_64:
        raise ValueError(f"member is not a 64-bit Mach-O object (magic 0x{magic:08x})")
    return cputype, cpusubtype


def archives_in_record(text: str) -> tuple[list[str], list[str]]:
    """Return (archive paths, unresolved -l names) from a link record."""
    tokens = text.split()
    libdirs = [token[2:] for token in tokens if token.startswith("-L") and len(token) > 2]
    paths: list[str] = []
    unresolved: list[str] = []
    for token in tokens:
        if token.startswith("-Wl,-force_load,"):
            paths.append(token.split(",", 2)[2])
        elif token.startswith("-l") and len(token) > 2:
            name = token[2:]
            for directory in libdirs:
                candidate = Path(directory) / f"lib{name}.a"
                if candidate.is_file():
                    paths.append(str(candidate))
                    break
            else:
                unresolved.append(token)
        elif token.endswith(".a") and not token.startswith("-"):
            paths.append(token)
    ordered: list[str] = []
    for path in paths:
        if path not in ordered:
            ordered.append(path)
    return ordered, unresolved


def run(argv: list[str], binary: bool = False):
    try:
        result = subprocess.run(argv, capture_output=True, text=not binary)
    except FileNotFoundError:
        raise SystemExit(2)
    if result.returncode != 0:
        raise SystemExit(1)
    return result.stdout


def declared_entries(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        digest = fields[0] if len(fields) == 2 and re.fullmatch(r"[0-9a-f]{64}", fields[0]) else ""
        target = fields[-1]
        entries[os.path.realpath(target)] = digest
    return entries


def under_roots(path: str, roots: list[str]) -> bool:
    real = os.path.realpath(path)
    for root in roots:
        base = os.path.realpath(root)
        if real == base or real.startswith(base + os.sep):
            return True
    return False


def check(paths: list[str], unresolved: list[str], kernel_arch: str, ar: str,
          roots: list[str], declared: dict[str, str], forbid: re.Pattern[str]) -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []
    want_subtype = CPU_SUBTYPE_ARM64E if kernel_arch == "arm64e" else 0
    arch_problems: list[str] = []
    if unresolved:
        arch_problems.append("unresolved: " + ", ".join(unresolved))
    counted = 0
    for path in paths:
        archive = Path(path)
        if not archive.is_file():
            arch_problems.append(f"{path} does not exist")
            continue
        members = [line.strip() for line in run([ar, "t", path]).splitlines() if line.strip()]
        if not members:
            arch_problems.append(f"{path} is empty")
            continue
        for member in members:
            try:
                cputype, cpusubtype = parse_member_header(run([ar, "p", path, member], binary=True))
            except ValueError as error:
                arch_problems.append(f"{path}({member}): {error}")
                break
            if cputype != CPU_TYPE_ARM64 or (cpusubtype & 0x00FFFFFF) != want_subtype:
                arch_problems.append(f"{path}({member}) is not {kernel_arch}")
                break
        counted += 1
    results.append((not arch_problems, "arch: " + ("; ".join(arch_problems) if arch_problems else f"{counted} archives, {kernel_arch}")))
    provenance_problems: list[str] = []
    for path in paths:
        if forbid.search(path):
            provenance_problems.append(f"{path} is named like a scratch stub")
            continue
        entry = declared.get(os.path.realpath(path))
        if declared:
            if entry is None:
                provenance_problems.append(f"{path} is not in the declared set")
            elif entry:
                actual = hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else "missing"
                if actual != entry:
                    provenance_problems.append(f"{path} sha256 {actual} does not match {entry}")
        elif roots:
            if not under_roots(path, roots):
                provenance_problems.append(f"{path} is outside every declared root")
        else:
            provenance_problems.append("no --allow-root or --declared given")
    results.append((not provenance_problems, "provenance: " + ("; ".join(provenance_problems) if provenance_problems else f"{len(paths)} archives declared")))
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check the 27 link inputs before they are used.")
    parser.add_argument("--link-record", required=True, help="linkarchives file from the kernel build")
    parser.add_argument("--kernel-arch", default="arm64e", choices=("arm64e", "arm64"))
    parser.add_argument("--allow-root", action="append", default=[])
    parser.add_argument("--declared", help="file of [sha256] path lines")
    parser.add_argument("--ar", default=os.environ.get("K60_AR", "llvm-ar"))
    parser.add_argument("--forbid", default=DEFAULT_FORBID)
    args = parser.parse_args(argv)
    record = Path(args.link_record)
    if not record.is_file():
        print(f"FAIL record: {record} does not exist", file=sys.stderr)
        return 2
    paths, unresolved = archives_in_record(record.read_text(encoding="utf-8"))
    declared: dict[str, str] = {}
    if args.declared:
        declared = declared_entries(Path(args.declared))
    results = check(paths, unresolved, args.kernel_arch, args.ar, args.allow_root, declared, re.compile(args.forbid))
    ok = True
    for passed, line in results:
        ok = ok and passed
        print(("PASS " if passed else "FAIL ") + line)
    if not ok:
        print("link inputs: FAIL", file=sys.stderr)
        return 1
    print(f"link inputs: PASS ({len(paths)} archives)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
