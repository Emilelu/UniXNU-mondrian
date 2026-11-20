#!/usr/bin/env python3
"""Compare the storage class vtable slot by slot, not by its length.

The 24A446 kernelcache keeps com.apple.iokit.IOStorageFamily as a separate
fileset entry.  Its __DATA_CONST holds the class vtable, but the pointer format
is dyld_chained_ptr_64_kernel_cache_rebase (format 8), not the ARM64E format a
first guess reaches for; decoding with the wrong format runs the table into its
neighbour and still produces a plausible count.

This tool reads N slots at --vtable, decodes format 8, and compares each slot
with docs/engineering/ios27-storage-vtable.tsv, which records the slot order,
the method and the arm64e discriminator that the pinned IOStorageFamily-337.100.1
source compiles to.  A slot is:

  一致       same discriminator, authenticated, target in the image the kind
             expects (own methods in the entry, external and pure virtual in
             com.apple.kernel)
  不一致     discriminator differs, or the target is code in the wrong image
  无法判定   the target is data, outside every segment, or not authenticated

The discriminator is a 16-bit hash, so a single match is evidence, not proof;
190 matches are the layout signature.  Nothing here runs on the board.

--require-entry turns the comparison into the assertion a preflight needs: every
slot must match on its discriminator, its authentication and its target image,
and the three words after the table must be zero.
"""

import argparse
import json
import struct
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
from collections import Counter
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
MH_FILESET = 12
LC_SEGMENT_64 = 0x19
LC_FILESET_ENTRY = 0x80000035
KERNEL_BASE = 0xFFFFFFF007004000
MASK30 = 0x3FFFFFFF


class Failure(Exception):
    pass


def parse_macho(data, base=0, name=None):
    if len(data) < base + 32 or struct.unpack_from('<I', data, base)[0] != MH_MAGIC_64:
        raise Failure(f'not a 64-bit Mach-O at {base:#x}')
    _, _, _, filetype, ncmds, sizeofcmds, _, _ = struct.unpack_from('<IiiIIIII', data, base)
    segments, entries = [], []
    off = base + 32
    end = off + sizeofcmds
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, off)
        if cmdsize < 8 or off + cmdsize > end:
            raise Failure(f'bad load command size {cmdsize} at {off:#x}')
        if cmd == LC_SEGMENT_64:
            segname, vmaddr, vmsize, fileoff, filesize = struct.unpack_from(
                '<16sQQQQ', data, off + 8)
            segments.append({'name': segname.split(b'\0', 1)[0].decode('ascii', 'replace'),
                             'vmaddr': vmaddr, 'vmsize': vmsize,
                             'fileoff': fileoff, 'filesize': filesize})
        elif cmd == LC_FILESET_ENTRY:
            _, fileoff, entry_id = struct.unpack_from('<QQI', data, off + 8)
            start = off + entry_id
            stop = data.find(b'\0', start)
            entries.append((data[start:stop].decode('ascii', 'replace'), fileoff))
        off += cmdsize
    node = {'name': name, 'base': base, 'filetype': filetype,
            'segments': segments, 'children': []}
    for child_name, fileoff in entries:
        node['children'].append(parse_macho(data, base + fileoff, child_name))
    return node


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


def find(node, name):
    for item in walk(node):
        if item['name'] == name:
            return item
    return None


def va_to_offset(entry, address, length):
    for segment in entry['segments']:
        start = segment['vmaddr']
        if start <= address and address + length <= start + segment['vmsize']:
            if segment['filesize'] < address - start + length:
                raise Failure(f'{address:#x} is beyond the file bytes of {segment["name"]}')
            return segment['fileoff'] + (address - start)
    raise Failure(f'{address:#x} is not inside any segment of {entry["name"]}')


def containing(entry, address):
    for segment in entry['segments']:
        if segment['vmaddr'] <= address < segment['vmaddr'] + segment['vmsize']:
            return segment['name']
    return None


def read_table(path, slots):
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('slot\t'):
            continue
        parts = line.split('\t')
        if len(parts) != 4:
            raise Failure(f'table row is not four columns: {line[:80]}')
        rows.append({'slot': int(parts[0]), 'kind': parts[1],
                     'method': parts[2], 'source_diversity': int(parts[3], 0)})
    if slots and len(rows) != slots:
        raise Failure(f'table has {len(rows)} rows, expected {slots}')
    for index, row in enumerate(rows):
        if row['slot'] != index:
            raise Failure(f'table row {index} claims slot {row["slot"]}')
    return rows


def classify(image, kernel, address):
    own = containing(image, address)
    if own in ('__TEXT', '__TEXT_EXEC'):
        return 'entry-code'
    if own:
        return 'data'
    other = containing(kernel, address)
    if other in ('__TEXT', '__TEXT_EXEC'):
        return 'kernel-code'
    if other:
        return 'data'
    return 'outside'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernelcache', required=True)
    parser.add_argument('--entry', default='com.apple.iokit.IOStorageFamily')
    parser.add_argument('--vtable', required=True, help='vtable address, e.g. 0xfffffff008314d88')
    parser.add_argument('--table', default=str(Path(__file__).resolve().parents[1]
                                              / 'docs/engineering/ios27-storage-vtable.tsv'))
    parser.add_argument('--slots', type=int, default=0, help='require this many slots')
    parser.add_argument('--out')
    parser.add_argument('--require-match', action='store_true',
                        help='exit 1 unless every slot is 一致')
    parser.add_argument('--require-entry', action='store_true',
                        help='exit 1 unless every slot matches on discriminator, '
                             'authentication and target image, and the tail is zero')
    args = parser.parse_args(argv)

    cache = Path(args.kernelcache)
    table_path = Path(args.table)
    if not cache.is_file():
        print(f'FAIL kernelcache {cache} not found')
        return 1
    if not table_path.is_file():
        print(f'FAIL table {table_path} not found')
        return 1
    try:
        data = cache.read_bytes()
        root = parse_macho(data)
        image = find(root, args.entry)
        if image is None:
            raise Failure(f'no fileset entry named {args.entry}')
        kernel = find(root, 'com.apple.kernel')
        if kernel is None:
            raise Failure('no com.apple.kernel entry to resolve external methods')
        rows = read_table(table_path, args.slots)
        vtable = int(args.vtable, 0)
        offset = va_to_offset(image, vtable, len(rows) * 8)
        # __ZTV starts with offset-to-top and typeinfo; slot 0 follows them.
        header = struct.unpack_from('<2Q', data, offset)
        if any(header):
            raise Failure(f'vtable header at {vtable:#x} is not two zero words')
        base_offset = offset + 16
        words = struct.unpack_from(f'<{len(rows)}Q', data, base_offset)
    except (OSError, ValueError, struct.error, Failure) as error:
        print(f'FAIL {error}')
        return 1

    verdicts = Counter()
    findings = []
    for row, word in zip(rows, words):
        target = word & MASK30
        diversity = (word >> 32) & 0xFFFF
        authenticated = (word >> 63) & 1
        address = KERNEL_BASE + target
        where = classify(image, kernel, address)
        expected = 'entry-code' if row['kind'] == 'own' else 'kernel-code'
        if diversity != row['source_diversity']:
            verdict, why = '不一致', f'discriminator {diversity:#x} != {row["source_diversity"]:#x}'
        elif not authenticated:
            verdict, why = '无法判定', 'pointer is not an authenticated rebase'
        elif where in ('data', 'outside'):
            verdict, why = '无法判定', f'target is in {where}, not code'
        elif where != expected:
            verdict, why = '不一致', f'target is {where}, expected {expected}'
        else:
            verdict, why = '一致', f'{row["kind"]} -> {where}'
        verdicts[verdict] += 1
        findings.append({**row, 'address': f'{address:#x}', 'where': where,
                         'diversity': diversity, 'authenticated': bool(authenticated),
                         'verdict': verdict, 'why': why})
        if verdict != '一致':
            print(f'  {verdict} slot {row["slot"]}: {row["method"]} at {address:#x} ({why})')

    # The table is followed by three zero words; a table that does not end there
    # is a table read past its end, which is how the wrong pointer format fails.
    tail = struct.unpack_from('<3Q', data, base_offset + len(rows) * 8) if \
        base_offset + len(rows) * 8 + 24 <= len(data) else ()
    tail_zero = bool(tail) and all(word == 0 for word in tail)
    strict = bool(args.require_match or args.require_entry)

    print(f'entry {args.entry}: {len(image["segments"])} segments, vtable {vtable:#x} (two-word header)')
    print(f'slots: {len(rows)} read at {vtable:#x}; '
          + ', '.join(f'{name} {count}' for name, count in verdicts.most_common()))
    print(f'tail: three words after the table are '
          + ('zero' if tail_zero else 'not all zero'))
    print('verdict: ' + ('all slots agree' if verdicts.get('一致', 0) == len(rows)
                         else f'{verdicts.get("不一致", 0)} disagree, '
                              f'{verdicts.get("无法判定", 0)} undecided'))

    result = {
        'kernelcache': str(cache),
        'entry': args.entry,
        'vtable': f'{vtable:#x}',
        'slots': len(rows),
        'tail_zero': tail_zero,
        'strict': strict,
        'counts': dict(verdicts),
        'findings': findings,
        'hardware_verified': False,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1) + '\n')
    if strict and (verdicts.get('一致', 0) != len(rows) or not tail_zero):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
