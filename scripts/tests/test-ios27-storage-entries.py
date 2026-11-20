#!/usr/bin/env python3
"""Tests for check-ios27-storage-entries.py.

The fixtures are synthetic kernel collections: an outer MH_FILESET whose entry
names are the only thing the checker reads. The real product answers "32
entries, none of them NativeUfs", and that answer is what decides whether route
B is implemented or still only designed.
"""

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'check-ios27-storage-entries.py'

CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def image():
    """A minimal MH_EXECUTE with no load commands; parse_macho only needs the header."""
    return struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 2, 2, 0, 0, 0, 0)


def fileset(names, filetype=12):
    """Build an outer image with one LC_FILESET_ENTRY per name.

    entry_id is relative to its own load command, which is the detail a reader
    gets wrong first: the name sits at command_start + entry_id, not at a file
    offset.
    """
    count = len(names)
    labels = b''
    label_offsets = []
    cursor = 32 + 32 * count
    for name in names:
        label_offsets.append(cursor + len(labels))
        labels += name.encode() + b'\0'
    inner_start = 32 + 32 * count + len(labels)
    inner_start += (-inner_start) % 8
    commands = b''
    for index, name in enumerate(names):
        command_start = 32 + 32 * index
        commands += struct.pack('<IIQQII', 0x80000035, 32, 0, inner_start + 32 * index,
                                label_offsets[index] - command_start, 0)
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 2, filetype, count, 32 * count, 0, 0)
    body = header + commands + labels
    body = body.ljust(inner_start, b'\0')
    return body + image() * count


def run(args):
    return subprocess.run([sys.executable, str(TOOL)] + args, capture_output=True, text=True)


def main():
    tmp = Path(tempfile.mkdtemp())
    product = ['com.apple.kernel', 'com.apple.kec.Libm', 'com.apple.iokit.IOStorageFamily',
               'com.apple.filesystems.apfs', 'com.apple.kec.corecrypto']

    # 1. a collection without the driver: the answer is a state, not an error
    path = tmp / 'without.bin'
    path.write_bytes(fileset(product))
    done = run(['--kernelcache', str(path)])
    case('a collection without the driver answers absent', 'ios27-storage-entries: absent' in done.stdout, done.stdout)
    case('an absent entry still exits 0', done.returncode == 0, str(done.returncode))
    case('the entry count is printed', 'entries: 5' in done.stdout, done.stdout)
    case('every entry name is listed', all(name in done.stdout for name in product))

    # 2. the driver as its own entry
    path = tmp / 'with.bin'
    path.write_bytes(fileset(product + ['com.apple.driver.NativeUfs']))
    done = run(['--kernelcache', str(path)])
    case('an entry named NativeUfs answers present', 'ios27-storage-entries: present' in done.stdout, done.stdout)
    case('the matching entry is named', 'matched NativeUfs in com.apple.driver.NativeUfs' in done.stdout, done.stdout)

    # 3. the other default spelling
    path = tmp / 'dash.bin'
    path.write_bytes(fileset(['com.apple.kernel', 'unixnu.native-ufs']))
    done = run(['--kernelcache', str(path)])
    case('the hyphenated bundle name is matched too', 'ios27-storage-entries: present' in done.stdout, done.stdout)

    # 4. --require-entry turns the finding into a failure
    path = tmp / 'require.bin'
    path.write_bytes(fileset(product))
    done = run(['--kernelcache', str(path), '--require-entry'])
    case('--require-entry fails when the entry is absent', done.returncode == 1, str(done.returncode))

    # 5. a custom pattern
    path = tmp / 'custom.bin'
    path.write_bytes(fileset(['com.apple.kernel', 'com.example.StorageThing']))
    done = run(['--kernelcache', str(path), '--match', 'StorageThing'])
    case('--match accepts another name', 'ios27-storage-entries: present' in done.stdout, done.stdout)

    # 6. an image that is not a fileset cannot answer the question
    path = tmp / 'plain.bin'
    path.write_bytes(image())
    done = run(['--kernelcache', str(path)])
    case('a plain executable fails loudly', done.returncode == 1 and 'not a fileset' in done.stdout, done.stdout)

    # 7. a missing file
    done = run(['--kernelcache', str(tmp / 'nope.bin')])
    case('a missing kernelcache fails', done.returncode == 1 and 'FAILED' in done.stdout, done.stdout)

    # 8. the report records the answer
    path = tmp / 'report.bin'
    path.write_bytes(fileset(product))
    out = tmp / 'report.json'
    done = run(['--kernelcache', str(path), '--out', str(out)])
    try:
        report = json.loads(out.read_text())
    except (OSError, ValueError):
        report = {}
    case('the report carries the verdict', report.get('verdict') == 'absent', json.dumps(report)[:200])
    case('the report counts the entries', report.get('entry_count') == len(product), report.get('entry_count'))
    case('the report lists the entries', report.get('entries') == product)
    case('the report never claims hardware', report.get('hardware_verified') is False)

    failed = [name for name, ok, _ in CASES if not ok]
    for name, ok, detail in CASES:
        if not ok:
            print(f'FAIL {name}')
            if detail:
                print(f'     {str(detail)[:400]}')
    if failed:
        print(f'TESTS FAILED {len(failed)} of {len(CASES)} case(s)')
        return 1
    print(f'TESTS OK {len(CASES)} case(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
