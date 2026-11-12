#!/usr/bin/env python3
"""Assemble the complete K60 unixnu partition image: OS + SystemOS + Data.

`unixnu build userdata` emits a version-1 SHNGROOT with the two IPSW windows
and has no way to add a file-backed Data window, while
drivers/NativeUfs/PongUfsTransport.cpp requires all three ("required SHNGROOT
window missing" otherwise).  This script appends a GPT-wrapped APFS Data disk
to that base image and commits a three-entry directory, entirely offline: no
adb, no recovery, no partition write.

Layout rules come from drivers/NativeUfs/RootLayout.h: version 1 only, at most
four entries, every entry block_size 512 / flags 1, offsets 4 KiB aligned and
non-overlapping, directory SHA-256 over bytes 0..4063 stored at 4064.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tomllib

MIB = 1 << 20
KIB4 = 4096
CHUNK = 8 << 20
HEADER_BYTES = 4096
ENTRY_BYTES = 128
ENTRY_BASE = 24
GPT_SIGNATURE = b'EFI PART'
REQUIRED = ('OS', 'SystemOS')


def align_up(value, unit):
    return (value + unit - 1) // unit * unit


def fail(message):
    raise SystemExit('build-k60-root-image: ' + message)


def read_directory(path):
    with path.open('rb') as handle:
        header = handle.read(HEADER_BYTES)
    if len(header) != HEADER_BYTES or header[:8] != b'SHNGROOT':
        fail(f'{path} does not start with a SHNGROOT directory')
    version, count, image_bytes = struct.unpack_from('<IIQ', header, 8)
    if version != 1:
        fail(f'{path} is SHNGROOT version {version}; this board accepts version 1 only')
    if not 1 <= count <= 4:
        fail(f'{path} declares {count} windows; RootLayout.h accepts 1..4')
    digest = hashlib.sha256(header[:HEADER_BYTES - 32]).digest()
    if digest != header[HEADER_BYTES - 32:]:
        fail(f'{path} directory hash does not match its bytes')
    entries = []
    for index in range(count):
        name, offset, size, block_size, flags, window_hash, _ = struct.unpack_from(
            '<32sQQII32s40s', header, ENTRY_BASE + index * ENTRY_BYTES)
        name = name.split(b'\0', 1)[0].decode()
        if block_size != 512 or flags != 1:
            fail(f'{path} window {name} has block_size={block_size} flags={flags}; '
                 'RootLayout.h requires 512/1')
        entries.append({'name': name, 'offset': offset, 'size': size,
                        'sha256': window_hash.hex()})
    entries.sort(key=lambda item: item['offset'])
    return {'path': str(path), 'image_bytes': image_bytes, 'windows': entries}


def partition_bytes_from_board(path):
    if not path.is_file():
        return None
    with path.open('rb') as handle:
        board = tomllib.load(handle)
    section = board.get('userdata') or {}
    first = section.get('first_lba')
    last = section.get('last_lba')
    unit = section.get('lba_bytes', 512)
    if first is None or last is None:
        return None
    return (last - first + 1) * unit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True,
                        help='SHNGROOT image produced by unixnu build userdata (OS+SystemOS)')
    parser.add_argument('--data', type=Path, required=True,
                        help='GPT-wrapped APFS Data disk (make-k60-gpt-data-image.py output)')
    parser.add_argument('--output', type=Path, required=True,
                        help='complete three-window image to write')
    parser.add_argument('--board', type=Path, default=Path('board.toml'),
                        help='board.toml used for the partition geometry and window names')
    parser.add_argument('--partition-bytes', type=lambda value: int(value, 0), default=None,
                        help='override the userdata partition capacity')
    parser.add_argument('--guard-mib', type=int, default=16,
                        help='gap kept between the last base window and Data (default 16)')
    parser.add_argument('--tail-reserve-mib', type=int, default=1024,
                        help='unallocated tail kept after Data (default 1024)')
    parser.add_argument('--dry-run', action='store_true', help='print the plan only')
    parser.add_argument('--force', action='store_true', help='overwrite the output file')
    args = parser.parse_args()

    base = read_directory(args.base)
    names = [window['name'] for window in base['windows']]
    if 'Data' in names:
        fail(f'{args.base} already carries a Data window ({names}); nothing to add')
    missing = [name for name in REQUIRED if name not in names]
    if missing:
        fail(f'{args.base} is missing {missing}; expected {list(REQUIRED)}')

    if not args.data.is_file():
        fail(f'missing Data disk image: {args.data}')
    data_bytes = args.data.stat().st_size
    if data_bytes < 1024 * 1024 or data_bytes % 512:
        fail(f'{args.data} must be a nonzero multiple of 512 bytes ({data_bytes})')
    with args.data.open('rb') as handle:
        handle.seek(512)
        if handle.read(8) != GPT_SIGNATURE:
            fail(f'{args.data} has no GPT header at offset 512; '
                 'PongUfsTransport publishes the Data window only for a GPT disk')

    partition_bytes = args.partition_bytes or partition_bytes_from_board(args.board)
    if not partition_bytes:
        fail('cannot determine the userdata partition size; pass --partition-bytes')

    last_end = max(window['offset'] + window['size'] for window in base['windows'])
    cursor = align_up(max(base['image_bytes'], last_end), MIB) + align_up(args.guard_mib * MIB, MIB)
    data_offset = align_up(cursor, KIB4)
    data_end = data_offset + data_bytes
    image_bytes = align_up(data_end, MIB)

    if data_offset < last_end:
        fail('computed Data offset overlaps the existing windows')
    if data_bytes > partition_bytes // 4:
        fail(f'Data disk {data_bytes} exceeds a quarter of the partition ({partition_bytes})')
    if image_bytes > partition_bytes - args.tail_reserve_mib * MIB:
        fail(f'image would end at {image_bytes}, leaving less than '
             f'{args.tail_reserve_mib} MiB of the {partition_bytes}-byte partition')

    report = {
        'base': base['path'],
        'data': str(args.data),
        'output': str(args.output),
        'partition_bytes': partition_bytes,
        'image_bytes': image_bytes,
        'windows': base['windows'] + [{'name': 'Data', 'offset': data_offset,
                                       'size': data_bytes}],
    }
    print(json.dumps(report, indent=2), flush=True)
    if args.dry_run:
        return
    if args.output.exists() and not args.force:
        fail(f'refusing to overwrite {args.output} (pass --force)')

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + '.partial')
    data_digest = hashlib.sha256()
    with temporary.open('wb') as output:
        output.truncate(image_bytes)

        copied = 0
        with args.base.open('rb', buffering=0) as source:
            while copied < base['image_bytes']:
                block = source.read(min(CHUNK, base['image_bytes'] - copied))
                if not block:
                    fail(f'short read from {args.base} at {copied}')
                output.seek(copied)
                output.write(block)
                copied += len(block)
        print(f'base: copied {copied} bytes', flush=True)

        output.seek(data_offset)
        written = 0
        with args.data.open('rb', buffering=0) as source:
            while written < data_bytes:
                block = source.read(min(CHUNK, data_bytes - written))
                if not block:
                    fail(f'short read from {args.data} at {written}')
                output.write(block)
                data_digest.update(block)
                written += len(block)
        print(f'Data: copied {written} bytes at offset {data_offset:#x}', flush=True)

        windows = [dict(window) for window in base['windows']]
        windows.append({'name': 'Data', 'offset': data_offset, 'size': data_bytes,
                        'sha256': data_digest.hexdigest()})
        windows.sort(key=lambda item: item['offset'])

        header = bytearray(HEADER_BYTES)
        header[:8] = b'SHNGROOT'
        struct.pack_into('<IIQ', header, 8, 1, len(windows), image_bytes)
        for index, window in enumerate(windows):
            struct.pack_into('<32sQQII32s40s', header, ENTRY_BASE + index * ENTRY_BYTES,
                             window['name'].encode(), window['offset'], window['size'],
                             512, 1, bytes.fromhex(window['sha256']), bytes(40))
        header[HEADER_BYTES - 32:] = hashlib.sha256(header[:HEADER_BYTES - 32]).digest()
        output.seek(0)
        output.write(header)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, args.output)

    written_report = dict(report)
    written_report['windows'] = windows
    report_path = args.output.with_suffix('.json')
    report_path.write_text(json.dumps(written_report, indent=2) + '\n')
    print(f'wrote {args.output} ({image_bytes} bytes); report {report_path}', flush=True)
    for window in windows:
        print(f"  {window['name']:<8} offset={window['offset']:#012x} "
              f"size={window['size']:#012x} sha256={window['sha256'][:16]}…", flush=True)


if __name__ == '__main__':
    main()
