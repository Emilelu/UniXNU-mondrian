#!/usr/bin/env python3
"""Verify the 13 silent `__auth_got` slots against the Apple kexts themselves.

The audit (`E:/k60-work/scratch/stubs/unreachable.toml`) records, for each of the
13 silent slots, the kext bundle, the slot address and the calling function.
This script re-derives the *binding* from the extracted 24A446 kexts:

  * the slot lives in `__DATA_CONST,__auth_got` of its bundle, at a known file
    offset;
  * the call site contains a `bl` to an entry of `__TEXT_EXEC,__auth_stubs`;
  * that stub's first `adrp`/`add`/`ldr` triplet resolves exactly to the slot.

It is deliberately a *kext-side* check: the kexts come from Apple's 24A446
kernelcache (sha256 fa07057b...), so the result is independent of which kernel
we build.  The kernel-side target addresses still come from build 20.

Usage (inside WSL, with the extracted kexts):
    python3 scripts/check-osservices27-sites.py \
        --kexts /home/emilelu/kc24A446/all \
        --unreachable /mnt/e/k60-work/scratch/stubs/unreachable.toml

Requires `llvm-objdump-18` for the `bl` lookup (only `__text` is disassembled;
`__auth_stubs` is decoded straight from the file bytes).
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python < 3.11
    import tomli as tomllib  # type: ignore

MARKER = "early_security_init"
DEFAULT_KEXTS = Path("/home/emilelu/kc24A446/all")
DEFAULT_UNREACHABLE = Path("/mnt/e/k60-work/scratch/stubs/unreachable.toml")


def parse_macho(path: Path):
    """Return (file bytes, sections) where sections are (seg, sect, addr, size, fileoff)."""
    data = path.read_bytes()
    magic, = struct.unpack_from("<I", data, 0)
    if magic != 0xFEEDFACF:
        raise ValueError(f"{path}: not a 64-bit Mach-O (magic {magic:#x})")
    ncmds, = struct.unpack_from("<I", data, 16)
    off = 32
    sections = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            nsects, = struct.unpack_from("<I", data, off + 64)
            p = off + 72
            for _s in range(nsects):
                sect = data[p:p + 16].rstrip(b"\0").decode()
                seg = data[p + 16:p + 32].rstrip(b"\0").decode()
                addr, ssize = struct.unpack_from("<QQ", data, p + 32)
                soff, = struct.unpack_from("<I", data, p + 48)
                sections.append((seg, sect, addr, ssize, soff))
                p += 80
        off += size
    return data, sections


def locate(sections, addr: int):
    for seg, sect, saddr, size, soff in sections:
        if saddr <= addr < saddr + size:
            return seg, sect, saddr, size, soff
    return None


def adrp_target(pc: int, word: int) -> int:
    immhi = (word >> 5) & 0x7FFFF
    immlo = (word >> 29) & 0x3
    imm = (immhi << 2) | immlo
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~0xFFF) + (imm << 12)


def add_imm(word: int) -> int:
    return (word >> 10) & 0xFFF


def call_site(sections, path: Path, call: int):
    """Return (instruction text, bl target) for the call site."""
    out = subprocess.run(
        ["llvm-objdump-18", "--macho", "--disassemble", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    pat = f"{call:016x}:"
    line = next((l for l in out if l.startswith(pat)), None)
    if line is None:
        raise AssertionError(f"{path.name}: no instruction at {call:#x}")
    m = re.search(r"\bbl\s+(0x[0-9a-f]+)", line)
    if not m:
        raise AssertionError(f"{path.name}: {call:#x} is not a bl: {line}")
    return line.split("\t")[-1].strip(), int(m.group(1), 16)


def check(kexts: Path, unreachable: Path) -> tuple[list[str], list[str]]:
    rows = [r for r in tomllib.loads(unreachable.read_text(encoding="utf-8"))["target"]
            if MARKER in r.get("reason", "")]
    errors: list[str] = []
    table: list[str] = []
    if len(rows) != 13:
        errors.append(f"unreachable.toml: expected 13 silent rows, found {len(rows)}")
    for r in rows:
        bundle, site = r["bundle"], int(r["site"], 16)
        path = kexts / bundle
        if not path.exists():
            errors.append(f"{bundle}: extracted kext missing at {path}")
            continue
        data, sections = parse_macho(path)
        loc = locate(sections, site)
        if not loc:
            errors.append(f"{bundle}: site {site:#x} outside every section")
            continue
        seg, sect, saddr, _ssize, soff = loc
        if (seg, sect) != ("__DATA_CONST", "__auth_got"):
            errors.append(f"{bundle}: site {site:#x} in {seg},{sect}, not __DATA_CONST,__auth_got")
        site_off = soff + (site - saddr)

        m = re.search(r"loaded by (0x[0-9a-f]+)\+(0x[0-9a-f]+)", r["reason"])
        if not m:
            errors.append(f"{bundle}: cannot parse the call site from reason")
            continue
        call = int(m.group(1), 16) + int(m.group(2), 16)
        text, stub = call_site(sections, path, call)
        sloc = locate(sections, stub)
        if not sloc:
            errors.append(f"{bundle}: stub {stub:#x} outside every section")
            continue
        sseg, ssect, saddr2, _sz, soff2 = sloc
        if (sseg, ssect) != ("__TEXT_EXEC", "__auth_stubs"):
            errors.append(f"{bundle}: stub {stub:#x} in {sseg},{ssect}, not __auth_stubs")
        stub_off = soff2 + (stub - saddr2)

        words = struct.unpack_from("<12I", data, stub_off)
        hits = []
        for i in range(0, 10, 2):
            if (words[i] & 0x9F000000) == 0x90000000:  # ADRP
                target = adrp_target(stub + i * 4, words[i]) + add_imm(words[i + 1])
                hits.append((i // 2, target))
        groups = [g for g, target in hits if target == site]
        if not groups:
            errors.append(f"{bundle}: no adrp/add in stub {stub:#x} resolves to {site:#x} "
                          f"(got {[hex(t) for _, t in hits]})")
            continue
        table.append(
            f"{site:#x}|{bundle}|{seg},{sect}|{site - saddr:#x}|{site_off:#x}|"
            f"{stub:#x}|{stub - saddr2:#x}|{groups[0]}|{call:#x}|{text}"
        )
    return errors, table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kexts", type=Path, default=DEFAULT_KEXTS)
    ap.add_argument("--unreachable", type=Path, default=DEFAULT_UNREACHABLE)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    errors, table = check(args.kexts, args.unreachable)
    if args.json:
        import json
        print(json.dumps({"ok": not errors, "rows": table, "errors": errors}, indent=2))
    else:
        for row in table:
            print(row)
        for err in errors:
            print(f"FAIL - {err}", file=sys.stderr)
        print(f"{'TESTS OK' if not errors else 'TESTS FAILED'} {len(table)}/13 rows")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
