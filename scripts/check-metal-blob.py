#!/usr/bin/env python3
"""Fail if the generated K60M container disagrees with its own length constant.

This is the gate for P-196. The first device boot with the Metal deploy reached
`K60METAL deploy files=5/6 error=22` because k60_metal_blob_len summed the raw
body sizes and omitted the 8-byte alignment padding between bodies, so the last
entry's offset sat past the end of the blob. Nothing in the build noticed: the
assembly is generated, so no compiler or linker check ever sees the table.

Checks, all against the generated .s:
  * the magic is K60M and the entry count matches the number of .incbin lines
  * every entry's [offset, offset+size) lies inside k60_metal_blob_len
  * entries are ordered, aligned and non-overlapping
  * every name is non-empty and shorter than 200 bytes

The path is always supplied by the caller (build-strict.sh passes the tree copy),
so this file never names a scratch location of its own (iron rule 1).
"""
import os
import struct
import sys
from pathlib import Path

REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])
ALIGN = 8


def parse_header(path: Path):
    head, incbins = [], 0
    lines = path.read_text().splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('.byte '):
            head.extend(int(x, 16) for x in stripped[len('.byte '):].split(','))
        elif stripped.startswith('.incbin'):
            incbins += 1
    blob_len = None
    for i, line in enumerate(lines):
        if line.strip() == '_k60_metal_blob_len:':
            blob_len = int(lines[i + 1].split()[-1])
            break
    return bytes(head), incbins, blob_len


def check(path: Path) -> list:
    problems = []
    head, incbins, blob_len = parse_header(path)
    if blob_len is None:
        return [f'{path}: no _k60_metal_blob_len label']
    if len(head) < 8:
        return [f'{path}: header truncated to {len(head)} bytes']
    magic, count = struct.unpack('<4sI', head[:8])
    if magic != b'K60M':
        problems.append(f'magic is {magic!r}, not K60M')
    if count != incbins:
        problems.append(f'container says {count} entries but the assembly has {incbins} .incbin lines')
    names_off = 8 + count * 10
    if names_off > len(head):
        return problems + [f'table of {count} entries does not fit in {len(head)} header bytes']

    name_total = 0
    previous_end = 0
    for idx in range(count):
        entry = head[8 + idx * 10:8 + idx * 10 + 10]
        name_len, size, offset = struct.unpack('<HII', entry)
        name = head[names_off + name_total:names_off + name_total + name_len]
        label = name.decode('utf-8', 'replace') or f'entry {idx}'
        name_total += name_len
        if name_len == 0:
            problems.append(f'[{idx}] has an empty name')
        elif name_len >= 200:
            problems.append(f'[{idx}] name is {name_len} bytes')
        if offset % ALIGN:
            problems.append(f'[{idx}] {label}: offset {offset} is not {ALIGN}-byte aligned')
        if offset < previous_end:
            problems.append(f'[{idx}] {label}: offset {offset} overlaps the previous body ending at {previous_end}')
        if offset > blob_len or size > blob_len - offset:
            problems.append(f'[{idx}] {label}: body [{offset},{offset + size}) runs past '
                            f'k60_metal_blob_len={blob_len} (P-196: the length must '
                            f'include the alignment padding between bodies)')
        previous_end = offset + size
    return problems


def main(argv) -> int:
    targets = [Path(a) for a in argv[1:]]
    if not targets:
        print('usage: check-metal-blob.py <generated .s> [...]')
        return 2
    missing = [t for t in targets if not t.is_file()]
    if missing:
        print(f'skip: {missing[0]} not generated yet (nothing to inspect)')
        return 0
    failed = False
    for target in targets:
        problems = check(target)
        if problems:
            failed = True
            print(f'❌ {target}')
            for p in problems:
                print(f'   - {p}')
        else:
            print(f'✅ {target}: container table is self-consistent')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
