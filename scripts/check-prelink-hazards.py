#!/usr/bin/env python3
"""Fail when the prelink left an unpinned address that no segment covers.

The kit reports `missing` addresses but does not stub them: rebind() returns the
original target when it has no pairing, so a wrong data pointer is silent until
something dereferences it. An address outside every segment of the collection is
the worst kind -- the first read is garbage or a data abort -- so each one must
be named in docs/engineering/IOS27-PRELINK-ALLOWLIST.toml with a reason and a
reviewer, or this check fails.

An address that *is* covered by a segment is not proven correct: it can point
into an unrelated segment. This check separates the hard fault risk from that
softer one instead of averaging both into one number.

Self-contained on purpose: the census must not depend on the internals of
check-ios27-artifacts.py, which changes shape often (P-220 family).

Usage:
    python3 scripts/check-prelink-hazards.py <board dir> [--list]
"""

import argparse
import json
import pathlib
import struct
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / 'docs/engineering/IOS27-PRELINK-ALLOWLIST.toml'

MH_MAGIC_64 = 0xFEEDFACF
MH_FILESET = 12
SEGMENT_CMD = 0x19
FILESET_ENTRY_CMD = 0x80000035


class Failure(Exception):
    pass


def entries(data):
    """The LC_FILESET_ENTRY list of a collection: file offset and identifier."""
    magic, _cpu, _subtype, filetype, ncmds, _size, _flags = struct.unpack_from(
        '<IiiIIII', data, 0)
    if magic != MH_MAGIC_64:
        raise Failure('the kernel is not a 64-bit Mach-O')
    if filetype != MH_FILESET:
        return []
    found = []
    offset = 32
    for _ in range(ncmds):
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8:
            raise Failure('a load command is shorter than its own header')
        if command == FILESET_ENTRY_CMD:
            _vmaddr, fileoff, entry_id = struct.unpack_from('<QQI', data, offset + 8)
            start = offset + entry_id
            end = data.index(0, start) if start < len(data) else start
            found.append({'offset': fileoff,
                          'identifier': data[start:end].decode('utf-8', 'replace')})
        offset += size
    return found


def segments(data, at):
    """(low, high, label) for every segment that has a size, of one header."""
    ncmds, sizeofcmds = struct.unpack_from('<II', data, at + 16)
    position, end = at + 32, at + 32 + sizeofcmds
    found = []
    for _ in range(ncmds):
        if position + 8 > end:
            break
        command, size = struct.unpack_from('<II', data, position)
        if command == SEGMENT_CMD and size >= 72:
            address, length, fileoff, _filesize = struct.unpack_from(
                '<QQQQ', data, position + 24)
            if length:
                found.append((address, address + length, 'fileoff %#x' % fileoff))
        position += size
    return found


def census(record, data):
    """Split unpinned addresses by whether any segment of the collection covers them."""
    ranges = segments(data, 0)
    for entry in entries(data):
        ranges.extend(segments(data, entry['offset']))
    total = covered = 0
    outside = []
    for bundle, addresses in sorted((record.get('missing') or {}).items()):
        for text in addresses:
            address = int(text, 0)
            total += 1
            if any(low <= address < high for low, high, _label in ranges):
                covered += 1
            else:
                outside.append((bundle, text))
    return {'total': total, 'covered': covered, 'outside': outside,
            'segments': len(ranges)}


def reviewed(path):
    if not path.is_file():
        raise Failure(f'{path} is missing; an empty allowlist still has to exist')
    with open(path, 'rb') as handle:
        data = tomllib.load(handle)
    slots = {}
    for entry in data.get('slot') or []:
        for key in ('bundle', 'address', 'reason', 'review'):
            if not entry.get(key):
                raise Failure(f'{path}: a slot is missing {key}')
        pair = (entry['bundle'], entry['address'])
        if pair in slots:
            raise Failure(f'{path}: {pair} is listed twice')
        slots[pair] = entry
    return slots


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('board', type=pathlib.Path)
    parser.add_argument('--list', action='store_true', help='print every outside slot')
    options = parser.parse_args(argv)

    kernel = options.board / 'kernel/kernel.macho'
    report = options.board / 'kernel/kernel.json'
    for path in (kernel, report):
        if not path.is_file():
            raise Failure(f'missing {path}: build the kernel first')

    record = json.loads(report.read_text())
    result = census(record, kernel.read_bytes())
    allow = reviewed(ALLOWLIST)

    print(f'unpinned: {result["total"]} address(es) in {len(record.get("missing") or {})} '
          f'bundle(s); {result["covered"]} covered by one of {result["segments"]} segment(s), '
          f'{len(result["outside"])} outside every segment')

    if options.list:
        for bundle, address in result['outside']:
            mark = 'reviewed' if (bundle, address) in allow else 'UNREVIEWED'
            print(f'  {mark:10s} {bundle} {address}')

    stray = [slot for slot in result['outside'] if slot not in allow]
    stale = [slot for slot in allow if slot not in result['outside']]
    if stale:
        print(f'note: {len(stale)} allowlist slot(s) are not in this report any more; '
              'delete them so the file keeps describing the current image')
    if stray:
        for bundle, address in stray[:10]:
            print(f'FAIL: {bundle} {address} is outside every segment and has no review')
        if len(stray) > 10:
            print(f'FAIL: and {len(stray) - 10} more')
        return 1
    print('ok prelink hazards: every outside-segment slot is reviewed')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Failure as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(2)
