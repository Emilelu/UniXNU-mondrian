#!/usr/bin/env python3
"""Check that the firmware's boot_args layout matches the kernel that reads it.

The platform writes DARWIN_BOOT_ARGS before hand-off; the kernel reads its own
struct boot_args from the same address.  When the two disagree, nothing fails at
build time: the loader writes plausible bytes and the kernel reads a different
field.  That is how a Darwin 22 header (608-byte command line) ended up writing
a Darwin 23 kernel's bootFlags from inside the command-line string.

This compares the loader header with the kernel header and fails when the
command-line capacity, the bootFlags offset, the memSizeActual offset or the
struct size disagree with the layout the kernel was compiled for.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# CommandLine capacity -> (bootFlags offset, memSizeActual offset, sizeof)
LAYOUTS = {
    608: (0x2D0, 0x2D8, 0x2E0),
    1024: (0x470, 0x478, 0x480),
}

DEFINE = re.compile(r'#define\s+(DARWIN_BOOT_LINE_LENGTH|BOOT_LINE_LENGTH)\s+(\d+)')
ARRAY = re.compile(r'CommandLine\s*\[\s*([A-Za-z_][A-Za-z0-9_]*|\d+)\s*\]')
ASSERT_OFFSET = re.compile(
    r'STATIC_ASSERT\s*\(\s*OFFSET_OF\s*\(\s*DARWIN_BOOT_ARGS\s*,\s*'
    r'(BootFlags|MemorySizeActual)\s*\)\s*==\s*(0x[0-9A-Fa-f]+|\d+)')
ASSERT_SIZE = re.compile(
    r'STATIC_ASSERT\s*\(\s*sizeof\s*\(\s*DARWIN_BOOT_ARGS\s*\)\s*==\s*(0x[0-9A-Fa-f]+|\d+)')


def read(path: Path) -> str:
    return path.read_text(errors='replace')


def number(text: str) -> int:
    return int(text, 0)


def check(header: Path, boot_h: Path) -> list[str]:
    problems: list[str] = []
    loader = read(header)
    kernel = read(boot_h)

    kernel_match = DEFINE.search(kernel)
    if not kernel_match or kernel_match.group(1) != 'BOOT_LINE_LENGTH':
        return [f'{boot_h}: BOOT_LINE_LENGTH not found']
    capacity = int(kernel_match.group(2))

    loader_match = DEFINE.search(loader)
    if loader_match and loader_match.group(1) == 'DARWIN_BOOT_LINE_LENGTH':
        loader_capacity = int(loader_match.group(2))
    else:
        array = ARRAY.search(loader)
        if not array:
            return [f'{header}: neither DARWIN_BOOT_LINE_LENGTH nor CommandLine[] found']
        token = array.group(1)
        loader_capacity = int(token) if token.isdigit() else 0

    if loader_capacity != capacity:
        problems.append(
            f'{header}: command line is {loader_capacity} bytes, the kernel reads {capacity}')

    layout = LAYOUTS.get(capacity)
    if layout is None:
        problems.append(f'{boot_h}: no known layout for a {capacity}-byte command line')
        return problems
    want_flags, want_mem, want_size = layout

    seen: dict[str, int] = {}
    for match in ASSERT_OFFSET.finditer(loader):
        seen[match.group(1)] = number(match.group(2))
    size_match = ASSERT_SIZE.search(loader)

    if seen.get('BootFlags') != want_flags:
        problems.append(
            f'{header}: BootFlags asserted at '
            f'{seen.get("BootFlags", -1):#x}, the {capacity}-byte layout needs {want_flags:#x}')
    if seen.get('MemorySizeActual') != want_mem:
        problems.append(
            f'{header}: MemorySizeActual asserted at '
            f'{seen.get("MemorySizeActual", -1):#x}, the {capacity}-byte layout needs {want_mem:#x}')
    if not size_match or number(size_match.group(1)) != want_size:
        got = number(size_match.group(1)) if size_match else -1
        problems.append(
            f'{header}: sizeof(DARWIN_BOOT_ARGS) is {got:#x}, the {capacity}-byte layout needs {want_size:#x}')
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--header', required=True, help='platform BootArgs.h')
    parser.add_argument('--boot-h', required=True, help='kernel pexpert boot.h')
    args = parser.parse_args()

    header = Path(args.header)
    boot_h = Path(args.boot_h)
    for path in (header, boot_h):
        if not path.is_file():
            print(f'BOOTARGS: {path} does not exist')
            return 2

    problems = check(header, boot_h)
    if problems:
        for problem in problems:
            print('FAIL ' + problem)
        return 1
    print('BOOTARGS OK the loader writes the layout the kernel reads')
    return 0


if __name__ == '__main__':
    sys.exit(main())
