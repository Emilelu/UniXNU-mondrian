#!/usr/bin/env python3
"""Check a built userdata image against concepts/userdata.md, three-state.

The official page fixes the SHNGROOT header (4096 bytes, version 1, 512-byte
blocks), the first window at 0x100000, 1 MiB alignment, a capacity ceiling and
the APFS volume UUID the kernel matches.  This gate reads the image itself, not
the builder's source: a builder can carry the right constants and still emit a
truncated or misaligned image.

Exit codes are part of the contract:

  0  the image exists and every checked field/UUID is correct
  1  the image exists but a field or the OS-window UUID is wrong
  2  the image (or the expected UUID) is absent/unreadable: cannot judge

2 is not a pass (P-279).  P-288 is the other trap: check-official-docs.py only
checks that this file exists and that the registry carries an assertion; it does
not execute this gate.  Run this command itself before calling the page mapped.

    python3 scripts/check-userdata-layout.py \
        --image out/pong-userdata-root/pong-userdata-root.img \
        --expect-uuid E3F4AED0-4454-4D5B-833C-E27E99C4F67B

The UUID is the OS window's APFS volume UUID (the page's root-matching value),
not the Data volume UUID.  1BCD69FF-24A5-48B1-94B6-8FE592B2F597 is the 16.6.1
Data volume and is deliberately a failing fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT / 'out/pong-userdata-root/pong-userdata-root.img'

HEADER_BYTES = 4096
FIRST_WINDOW = 0x100000
WINDOW_ALIGN = 0x100000
BLOCK_BYTES = 512
ENTRY_BYTES = 128
ENTRY_FORMAT = '<32sQQII32s40s'
# A raw APFS container keeps its first volume superblock at 0xa2020 and the
# volume UUID at +0xd0 (docs/devices/mondrian-mzyxsl.md:266, same layout the
# seed scan used).  The OS window starts at the SHNGROOT first-window offset.
VOLUME_SUPERBLOCK = 0xA2020
VOLUME_UUID_OFFSET = 0xD0
FLAG_READ_ONLY = 1
MAX_WINDOWS = (HEADER_BYTES - 24) // ENTRY_BYTES
EXIT_OK = 0
EXIT_BAD = 1
EXIT_CANNOT_JUDGE = 2


def normalise(value: str) -> str:
    return str(uuid.UUID(value.strip().strip('{}'))).upper()


def read_header(path: Path) -> bytes:
    with path.open('rb') as stream:
        return stream.read(HEADER_BYTES)


def parse_header(header: bytes, image_bytes: int) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    if len(header) < HEADER_BYTES:
        return [], [f'header is {len(header)} bytes, not {HEADER_BYTES}']
    if header[:8] != b'SHNGROOT':
        problems.append(f'magic is {header[:8]!r}, not b\'SHNGROOT\'')
    version, count, declared = struct.unpack_from('<IIQ', header, 8)
    if version != 1:
        problems.append(f'header version is {version}, not 1')
    if count == 0:
        problems.append('header declares no windows')
    if count > MAX_WINDOWS:
        problems.append(f'header declares {count} windows, the 4096-byte header holds at most {MAX_WINDOWS}')
    if declared != image_bytes:
        problems.append(f'header image_bytes is {declared}, file is {image_bytes} bytes')
    if header[4064:4096] != hashlib.sha256(header[:4064]).digest():
        problems.append('header SHA-256 at 4064 does not cover the first 4064 bytes')
    windows: list[dict] = []
    for index in range(min(count, MAX_WINDOWS)):
        at = 24 + index * ENTRY_BYTES
        name, offset, size, block, flags, digest, reserved = struct.unpack_from(ENTRY_FORMAT, header, at)
        label = name.split(b'\0', 1)[0].decode('utf-8', 'replace') or f'window {index}'
        windows.append({'name': label, 'offset': offset, 'size': size,
                        'block': block, 'flags': flags, 'sha256': digest, 'reserved': reserved})
        if offset < FIRST_WINDOW:
            problems.append(f'{label}: offset {offset:#x} is below the first window {FIRST_WINDOW:#x}')
        if offset % WINDOW_ALIGN:
            problems.append(f'{label}: offset {offset:#x} is not {WINDOW_ALIGN:#x}-aligned')
        if size == 0:
            problems.append(f'{label}: size is zero')
        if offset + size > image_bytes:
            problems.append(f'{label}: [{offset:#x}, {offset + size:#x}) runs past the {image_bytes}-byte image')
        if block != BLOCK_BYTES:
            problems.append(f'{label}: block_size is {block}, not {BLOCK_BYTES}')
        if flags & ~FLAG_READ_ONLY:
            problems.append(f'{label}: flags {flags:#x} carry bits other than read-only')
        if digest == bytes(32):
            problems.append(f'{label}: window SHA-256 is all zero')
    if windows:
        if windows[0]['offset'] != FIRST_WINDOW:
            problems.append(f'first window starts at {windows[0]["offset"]:#x}, not {FIRST_WINDOW:#x}')
    return windows, problems


def diagnose(image: Path, expect_uuid: str | None,
             capacity: int | None = None) -> tuple[int, list[str]]:
    image = Path(image)
    if not image.is_file():
        return EXIT_CANNOT_JUDGE, [f'cannot judge: {image} does not exist (P-279)']
    if not expect_uuid:
        return EXIT_CANNOT_JUDGE, ['cannot judge: no --expect-uuid was supplied (P-279)']
    try:
        expected = normalise(expect_uuid)
    except ValueError:
        return EXIT_CANNOT_JUDGE, [f'cannot judge: --expect-uuid {expect_uuid!r} is not a UUID (P-279)']
    try:
        image_bytes = image.stat().st_size
        header = read_header(image)
    except OSError as error:
        return EXIT_CANNOT_JUDGE, [f'cannot judge: {image}: {error} (P-279)']
    windows, problems = parse_header(header, image_bytes)
    if capacity is not None and image_bytes > capacity:
        problems.append(f'image is {image_bytes} bytes, capacity is {capacity}')
    if not windows:
        problems.append('no window could be read, the OS-window UUID cannot be checked')
    if windows:
        first = windows[0]['offset']
        uuid_at = first + VOLUME_SUPERBLOCK + VOLUME_UUID_OFFSET
        if uuid_at + 16 > image_bytes:
            problems.append(f'OS-window UUID offset {uuid_at:#x} is past the {image_bytes}-byte image')
        else:
            try:
                with image.open('rb') as stream:
                    stream.seek(uuid_at)
                    raw = stream.read(16)
                actual = str(uuid.UUID(bytes=raw)).upper()
            except (OSError, ValueError) as error:
                problems.append(f'OS-window UUID at {uuid_at:#x} is unreadable: {error}')
            else:
                if actual == '00000000-0000-0000-0000-000000000000':
                    problems.append(f'OS-window UUID at {uuid_at:#x} is all zero')
                elif actual != expected:
                    note = ''
                    if actual == '1BCD69FF-24A5-48B1-94B6-8FE592B2F597':
                        note = ' (that is the 16.6.1 Data UUID, not the OS-window UUID)'
                    problems.append(f'OS-window UUID is {actual}, expected {expected}{note}')
    if problems:
        return EXIT_BAD, problems
    return EXIT_OK, [f'userdata-layout: OK (SHNGROOT v1, {len(windows)} window(s), '
                     f'first {FIRST_WINDOW:#x}, {WINDOW_ALIGN:#x} alignment, '
                     f'{BLOCK_BYTES}-byte blocks; OS-window UUID {expected})']


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='three-state SHNGROOT/userdata image gate')
    parser.add_argument('--image', type=Path, default=DEFAULT_IMAGE, help='built userdata image')
    parser.add_argument('--expect-uuid', help='OS window APFS volume UUID (root-matching value)')
    parser.add_argument('--capacity', type=lambda value: int(value, 0),
                        help='optional userdata capacity in bytes; 0x... accepted')
    parser.add_argument('--json', action='store_true', help='machine-readable result')
    options = parser.parse_args(argv)
    code, messages = diagnose(options.image, options.expect_uuid, options.capacity)
    if options.json:
        print(json.dumps({'image': str(options.image), 'exit': code,
                          'problems': messages if code else [],
                          'ok': code == EXIT_OK}, ensure_ascii=False, indent=2))
    else:
        if code == EXIT_CANNOT_JUDGE:
            for message in messages:
                print(f'CANNOT JUDGE: {message}')
        elif code == EXIT_BAD:
            for message in messages:
                print(f'FAIL {message}')
        else:
            print(messages[0])
    return code


if __name__ == '__main__':
    sys.exit(main())
