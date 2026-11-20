#!/usr/bin/env python3
"""Say whether the owner targets in a prelink report can be named at all.

The prelink emitter resolves every cross-image reference through the target
kernel's symbol table.  When that table is empty the resolver has nothing to
match, every owner target becomes "missing", and every site is redirected to
_unixnu_fileset_unmapped.  That is a property of the input collection, not of
a flag, so this tool separates the two claims:

  closure-needs-symbols   the input kernel entry carries no symbols, so no
                          owner target can be named by any setting
  closure-resolvable      every target address has a defined symbol
  partial                 some targets are named, some are not

Usage:
  python3 scripts/check-ios27-prelink-closure.py --report kernel.json \
      --kernelcache kernelcache.decompressed

The kernelcache may be the pinned input (a fileset) or a plain MH_EXECUTE.
Nothing here writes to the report directory, and hardware_verified is false.
"""

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
MH_FILESET = 12
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_FILESET_ENTRY = 0x80000035


class Failure(Exception):
    pass


def u32(data, off):
    return struct.unpack_from('<I', data, off)[0]


def parse_macho(data, base=0, name=None):
    if len(data) < base + 32:
        raise Failure(f'truncated Mach-O at {base:#x}')
    magic = u32(data, base)
    if magic != MH_MAGIC_64:
        raise Failure(f'not a 64-bit Mach-O at {base:#x} (magic {magic:#x})')
    _, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, _ = struct.unpack_from(
        '<IiiIIIII', data, base)
    segments, symtab, entries = [], None, []
    off = base + 32
    end = off + sizeofcmds
    for _ in range(ncmds):
        if off + 8 > end:
            raise Failure(f'load command runs past sizeofcmds at {off:#x}')
        cmd, cmdsize = struct.unpack_from('<II', data, off)
        if cmdsize < 8 or off + cmdsize > end:
            raise Failure(f'bad load command size {cmdsize} at {off:#x}')
        if cmd == LC_SEGMENT_64:
            segname, vmaddr, vmsize, fileoff, filesize = struct.unpack_from(
                '<16sQQQQ', data, off + 8)
            segments.append({
                'name': segname.split(b'\0', 1)[0].decode('ascii', 'replace'),
                'vmaddr': vmaddr, 'vmsize': vmsize,
                'fileoff': fileoff, 'filesize': filesize,
            })
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', data, off + 8)
            symtab = {'symoff': symoff, 'nsyms': nsyms,
                      'stroff': stroff, 'strsize': strsize}
        elif cmd == LC_FILESET_ENTRY:
            vmaddr, fileoff, entry_id = struct.unpack_from('<QQI', data, off + 8)
            start = off + entry_id
            stop = data.find(b'\0', start)
            child_name = data[start:stop].decode('ascii', 'replace') if stop > start else ''
            entries.append((child_name, fileoff))
        off += cmdsize
    node = {
        'name': name, 'base': base, 'filetype': filetype,
        'cputype': cputype, 'cpusubtype': cpusubtype,
        'ncmds': ncmds, 'segments': segments, 'symtab': symtab,
        'children': [],
    }
    for child_name, fileoff in entries:
        node['children'].append(parse_macho(data, base + fileoff, child_name))
    return node


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


def find_kernel(node):
    for item in walk(node):
        if item['name'] == 'com.apple.kernel':
            return item
    if node['filetype'] != MH_FILESET:
        return node
    for item in walk(node):
        if item['filetype'] == 2:
            return item
    return None


def symbol_values(data, entry):
    table = entry['symtab']
    values = set()
    if not table:
        return values
    symoff, nsyms, stroff = table['symoff'], table['nsyms'], table['stroff']
    if entry['base'] + symoff + nsyms * 16 > len(data):
        raise Failure(f'symbol table runs past the file ({nsyms} entries)')
    for index in range(nsyms):
        _, n_type, _, _, n_value = struct.unpack_from(
            '<IBBHQ', data, entry['base'] + symoff + index * 16)
        if n_type & 0x0E:  # a defined section or absolute symbol
            values.add(n_value)
    return values


def references(record, key):
    """Return (distinct addresses, total references) for one report section."""
    addresses, total = set(), 0
    for value in (record.get(key) or {}).values():
        if isinstance(value, dict):
            for address, count in value.items():
                addresses.add(address)
                total += int(count)
        elif isinstance(value, list):
            for address in value:
                addresses.add(str(address))
                total += 1
        else:
            addresses.add(str(value))
            total += 1
    return addresses, total


def segment_of(entry, address):
    for segment in entry['segments']:
        start = segment['vmaddr']
        if start <= address < start + segment['vmsize']:
            return segment['name']
    return None


def layout_segments(record):
    layout = (record.get('statistics') or {}).get('segment_layout') or {}
    space = 'new' if 'output' in str(record.get('missing_address_space', '')) else 'old'
    segments = []
    for name, value in layout.items():
        try:
            segments.append((name, int(value[space], 16), int(value['size'], 16)))
        except (KeyError, TypeError, ValueError):
            return space, []
    return space, segments


def segment_in(segments, address):
    for name, start, size in segments:
        if start <= address < start + size:
            return name
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, help='kernel.json from the prelink emitter')
    parser.add_argument('--kernelcache', required=True, help='the input kernel or kernelcache')
    parser.add_argument('--out', help='write the findings as JSON')
    parser.add_argument('--require-named', action='store_true',
                        help='exit 1 unless every owner target has a symbol')
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    cache_path = Path(args.kernelcache)
    if not report_path.is_file():
        print(f'FAIL report {report_path} not found')
        return 1
    if not cache_path.is_file():
        print(f'FAIL kernelcache {cache_path} not found')
        return 1
    try:
        record = json.loads(report_path.read_text())
        data = cache_path.read_bytes()
        root = parse_macho(data)
        kernel = find_kernel(root)
        if kernel is None:
            raise Failure('no com.apple.kernel entry and no plain executable')
    except (OSError, ValueError, Failure) as error:
        print(f'FAIL {error}')
        return 1

    missing, missing_refs = references(record, 'missing')
    stubbed, stub_refs = references(record, 'stubbed')
    table = kernel['symtab'] or {'nsyms': 0}
    values = symbol_values(data, kernel)
    space, layout = layout_segments(record)
    if layout:
        by_segment = Counter(segment_in(layout, int(address, 0)) or 'outside-collection'
                             for address in missing)
        space_label = f'the {space} layout ({record.get("missing_address_space")})'
    else:
        by_segment = Counter(segment_of(kernel, int(address, 0)) or 'outside-original-entry'
                             for address in missing)
        space_label = 'the input kernel entry'
    nameable = sum(1 for address in missing if int(address, 0) in values)

    prelink_sizes = {segment['name']: segment['vmsize']
                     for segment in kernel['segments']
                     if segment['name'].startswith(('__PRELINK', '__PLK'))}
    zero_prelink = all(size == 0 for size in prelink_sizes.values()) if prelink_sizes else None

    if not missing:
        verdict = 'closure-resolvable'
        reason = 'the report carries no missing owner target'
    elif table['nsyms'] == 0:
        verdict = 'closure-needs-symbols'
        reason = ('the input kernel entry has no symbol table, so a symbol-level '
                  'prelink cannot name any owner target')
    elif nameable == len(missing):
        verdict = 'closure-resolvable'
        reason = 'every owner target address has a defined symbol'
    elif nameable:
        verdict = 'partial'
        reason = f'{nameable} of {len(missing)} owner targets have a defined symbol'
    else:
        verdict = 'closure-needs-symbols'
        reason = ('the input kernel has symbols, but none sits at a missing '
                  'owner target address')

    print(f'report: {len(record.get("missing") or {})} missing bundles, '
          f'{len(missing)} symbols, {missing_refs} references')
    print(f'stub:   {len(record.get("stubbed") or {})} bundles, '
          f'{len(stubbed)} sites, {stub_refs} references')
    print(f'kernel: {kernel["name"] or "(plain)"} filetype {kernel["filetype"]}, '
          f'{kernel["ncmds"]} load commands, nsyms {table["nsyms"]}')
    if prelink_sizes:
        joined = ', '.join(f'{name} {size:#x}' for name, size in sorted(prelink_sizes.items()))
        print(f'prelink segments: {joined}')
    print(f'targets: {len(missing)} distinct, {nameable} nameable, in {space_label}; '
          f'segments: ' + ', '.join(f'{name} {count}' for name, count in by_segment.most_common()))
    print(f'verdict: {verdict} -- {reason}')

    result = {
        'report': str(report_path),
        'kernelcache': str(cache_path),
        'kernel_entry': kernel['name'],
        'kernel_filetype': kernel['filetype'],
        'kernel_nsyms': table['nsyms'],
        'prelink_segments': prelink_sizes,
        'prelink_segments_all_zero': zero_prelink,
        'missing_bundles': len(record.get('missing') or {}),
        'missing_symbols': len(missing),
        'missing_references': missing_refs,
        'stubbed_bundles': len(record.get('stubbed') or {}),
        'stubbed_sites': len(stubbed),
        'stubbed_references': stub_refs,
        'missing_address_space': record.get('missing_address_space', ''),
        'targets_by_segment': dict(by_segment),
        'targets_outside_collection': by_segment.get('outside-collection', 0)
        + by_segment.get('outside-original-entry', 0),
        'nameable_targets': nameable,
        'verdict': verdict,
        'reason': reason,
        'hardware_verified': False,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1) + '\n')
    if args.require_named and verdict != 'closure-resolvable':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
