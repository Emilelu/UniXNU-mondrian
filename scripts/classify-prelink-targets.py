#!/usr/bin/env python3
"""Where do the stubbed prelink targets live: our text segment, another link layout, or nowhere?

The stubbed targets come out of Apple's kernelcache, so their addresses are in Apple's link layout.
Comparing them against our own kernel by address therefore answers nothing unless both were linked
the same way. This script makes that explicit instead of leaving it as an assumption: it prints each
kernel's __TEXT_EXEC range, how many symbols fall inside it, and how the targets land.

Mach kernels put code in __TEXT_EXEC, which llvm-nm reports as a generic section symbol ('s'/'S')
rather than 't'/'T', so filtering by symbol kind alone reads as "no functions at all" -- that was the
first bug here, recorded in P-289's family.

Usage:
  python3 scripts/classify-prelink-targets.py [--record PATH] [--kernel PATH] [--reference PATH]
"""
import argparse
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

RECORD = Path('/mnt/e/k60-work/scratch/stubs/unreachable.toml')
NM = '/usr/bin/llvm-nm-18'
DEV = Path('/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/'
           'DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf')
REF = Path('/mnt/e/hackios/k60-gates/scripts/xnu-fileset-reference/'
           'mach.release.bcm2837.unstripped.noctf')
SEGMENT = 0x19


def segments(data: bytes, at: int = 0):
    """Yield (name, vmaddr, vmsize) for every LC_SEGMENT_64 at `at`."""
    magic, _, _, _, ncmds, _ = struct.unpack_from('<IiiIII', data, at)
    if magic != 0xfeedfacf:
        raise SystemExit(f'not a MH_MAGIC_64 image at {at:#x}')
    offset = at + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, offset)
        if cmd == SEGMENT:
            name = data[offset + 8:offset + 24].split(b'\0')[0].decode('ascii', 'replace')
            address, vmsize = struct.unpack_from('<QQ', data, offset + 24)
            yield name, address, vmsize
        offset += size


def text_range(path: Path):
    with path.open('rb') as handle:
        head = handle.read(0x4000)
    for name, address, vmsize in segments(head):
        if name == '__TEXT_EXEC':
            return address, address + vmsize
    raise SystemExit(f'no __TEXT_EXEC segment in {path.name}')


def symbols(path: Path, low: int, high: int) -> dict:
    out = subprocess.run([NM, '-n', '--defined-only', str(path)], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f'{NM} failed on {path.name}: {out.stderr.strip()[:200]}')
    starts = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            address = int(parts[0], 16)
        except ValueError:
            continue
        if low <= address < high:
            starts[address] = parts[2]
    return starts


def classify(targets, starts):
    ordered = sorted(starts)
    exact, inside, below = [], [], []
    for address in targets:
        if address in starts:
            exact.append((address, starts[address]))
            continue
        lo, hi = 0, len(ordered)
        while lo < hi:
            mid = (lo + hi) // 2
            if ordered[mid] <= address:
                lo = mid + 1
            else:
                hi = mid
        if lo:
            inside.append((address, starts[ordered[lo - 1]], address - ordered[lo - 1]))
        else:
            below.append(address)
    return exact, inside, below


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', default=str(RECORD))
    parser.add_argument('--kernel', default=str(DEV))
    parser.add_argument('--reference', default=str(REF))
    arguments = parser.parse_args()

    record = tomllib.loads(Path(arguments.record).read_text(encoding='utf-8'))
    stanzas = record['target']
    targets = sorted({int(stanza['target'], 16) for stanza in stanzas})
    print(f'record: {len(stanzas)} stanza(s), {len(targets)} unique target address(es)')
    print(f'target range: {targets[0]:#x}..{targets[-1]:#x}')

    for label, path in (('kernel', Path(arguments.kernel)), ('reference', Path(arguments.reference))):
        if not path.is_file():
            print(f'{label}: absent at {path}')
            continue
        low, high = text_range(path)
        starts = symbols(path, low, high)
        exact, inside, below = classify(targets, starts)
        print(f'{label}: __TEXT_EXEC {low:#x}..{high:#x}, {len(starts)} symbols in range')
        print(f'  exact start {len(exact)} | inside a function {len(inside)} | below the first {len(below)}')
        for address, name in exact[:4]:
            print(f'    exact  {address:#x} {name}')
        for address, name, delta in inside[:4]:
            print(f'    inside {address:#x} {name}+{delta:#x}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
