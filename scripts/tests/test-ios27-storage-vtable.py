#!/usr/bin/env python3
"""Tests for check-ios27-storage-vtable.py.

The fixtures are synthetic filesets: one entry named after the storage family
with a vtable in __DATA_CONST, and a com.apple.kernel entry whose __TEXT_EXEC
holds the external methods.  Segment file offsets are absolute in the outer
collection, the way a real kernel collection records them, so a reader that
adds the entry base again lands in the middle of the next image.
"""

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'check-ios27-storage-vtable.py'
CASES = []
BASE = 0xFFFFFFF007004000


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def macho(segments, filetype=2, size=0x3000, words_at=None, words=(), placement=0):
    commands = b''
    for name, vmaddr, vmsize, fileoff in segments:
        commands += struct.pack('<II16sQQQQiiII', 0x19, 72, name.encode(),
                                vmaddr, vmsize, placement + fileoff, size, 7, 5, 0, 0)
    header = struct.pack('<IIiIIIII', 0xFEEDFACF, 0x0100000C, -2147483646,
                         filetype, len(segments), len(commands), 0x00200085, 0)
    data = bytearray(size)
    data[0:32] = header
    data[32:32 + len(commands)] = commands
    if words_at is not None:
        blob = b''.join(struct.pack('<Q', word) for word in words)
        data[words_at:words_at + len(blob)] = blob
    return bytes(data)


def fileset(children):
    """children: (name, factory) where factory(placement) returns the image."""
    placements, offset = [], 0x1000
    for _, factory in children:
        placements.append(offset)
        offset += (len(factory(0)) + 0xFFF) & ~0xFFF
    commands, blobs = b'', {}
    for (name, factory), placement in zip(children, placements):
        body = name.encode() + b'\0'
        cmdsize = 32 + len(body)
        cmdsize += (8 - cmdsize % 8) % 8
        cmd = struct.pack('<IIQQII', 0x80000035, cmdsize, 0,
                          placement, 32, 0) + body
        cmd += b'\0' * (cmdsize - 32 - len(body))
        commands += cmd
        blobs[placement] = factory(placement)
    size = offset
    header = struct.pack('<IIiIIIII', 0xFEEDFACF, 0x0100000C, -2147483646,
                         12, len(children), len(commands), 0x00200085, 0)
    data = bytearray(size)
    data[0:32] = header
    data[32:32 + len(commands)] = commands
    for at, blob in blobs.items():
        data[at:at + len(blob)] = blob
    return bytes(data)


def word(address, diversity, authenticated=1):
    target = address - BASE
    assert 0 <= target <= 0x3FFFFFFF, hex(target)
    return (authenticated << 63) | (diversity << 32) | target


PIN = '7edb88fbae296fb7c8ce2f64e115e116e566d51c'


def table(rows, commit=PIN):
    out = '# pin: IOStorageFamily IOStorageFamily-337.100.1\n'
    if commit:
        out += f'# commit: {commit}\n'
    out += '# source: profiles/os/ios-27.0.1-24A446/profile.toml\n'
    out += 'slot\tkind\tmethod\tsource_diversity\n'
    for slot, kind, method, div in rows:
        out += f'{slot}\t{kind}\t{method}\t{div:#x}\n'
    return out


def run(args, tmp):
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, text=True, encoding='utf-8', cwd=tmp)


def main():
    tmp = Path(tempfile.mkdtemp(prefix='vtable-'))
    rows = [(0, 'own', '__ZN20IOBlockStorageDeviceD1Ev', 0x1111),
            (1, 'external', '__ZNK8OSObject7releaseEv', 0x2222),
            (2, 'pure', '___cxa_pure_virtual', 0x3333)]

    def image(placement):
        return macho([('__TEXT', 0xFFFFFFF007A00000, 0x1000, 0),
                      ('__TEXT_EXEC', 0xFFFFFFF007A10000, 0x1000, 0),
                      ('__DATA_CONST', 0xFFFFFFF007A20000, 0x1000, 0x1000)],
                     filetype=11, words_at=0x1000,
                     words=[0, 0, word(0xFFFFFFF007A10100, 0x1111),
                            word(0xFFFFFFF00AB48100, 0x2222),
                            word(0xFFFFFFF00AB48200, 0x3333), 0, 0, 0],
                     placement=placement)

    def kernel(placement):
        return macho([('__TEXT_EXEC', 0xFFFFFFF00AB48000, 0x1000, 0)],
                     placement=placement)

    cache = tmp / 'cache.bin'
    cache.write_bytes(fileset([('com.apple.kernel', kernel),
                               ('com.apple.iokit.IOStorageFamily', image)]))
    table_path = tmp / 'table.tsv'
    table_path.write_text(table(rows))
    args = ['--kernelcache', str(cache), '--vtable', '0xFFFFFFF007A20000',
            '--table', str(table_path)]

    # 1. three slots, each in the image its kind expects
    done = run(args, tmp)
    case('the fixture is accepted', done.returncode == 0, done.stderr)
    case('all three slots agree', 'all slots agree' in done.stdout, done.stdout)
    case('the slot count is printed', 'slots: 3 read' in done.stdout, done.stdout)
    case('the zero tail is confirmed', 'three words after the table are zero' in done.stdout, done.stdout)

    # 1b. the entry assertion covers every property, not just the count
    done = run(args + ['--require-entry'], tmp)
    case('--require-entry passes on a matching entry', done.returncode == 0, done.stdout)

    # 1c. the table is tied to the pin it came from
    profile = tmp / 'profile.toml'
    profile.write_text('[[source]]\nname = "IOStorageFamily"\n'
                       'ref = "IOStorageFamily-337.100.1"\n'
                       f'commit = "{PIN}"\n')
    done = run(args + ['--profile', str(profile)], tmp)
    case('the table pin matches the profile', done.returncode == 0, done.stdout)

    moved = tmp / 'moved.toml'
    moved.write_text('[[source]]\nname = "IOStorageFamily"\n'
                     'commit = "0000000000000000000000000000000000000000"\n')
    done = run(args + ['--profile', str(moved)], tmp)
    case('a moved pin turns the table red',
         done.returncode == 1 and 'table pin' in done.stdout, done.stdout)

    unpinned = tmp / 'unpinned.tsv'
    unpinned.write_text(table(rows, commit=None))
    done = run(args[:-1] + [str(unpinned)], tmp)
    case('a table that records no pin is red',
         done.returncode == 1 and 'records no' in done.stdout, done.stdout)

    def unauth_image(placement):
        return macho([('__TEXT', 0xFFFFFFF007A00000, 0x1000, 0),
                      ('__TEXT_EXEC', 0xFFFFFFF007A10000, 0x1000, 0),
                      ('__DATA_CONST', 0xFFFFFFF007A20000, 0x1000, 0x1000)],
                     filetype=11, words_at=0x1000,
                     words=[0, 0, word(0xFFFFFFF007A10100, 0x1111),
                            word(0xFFFFFFF00AB48100, 0x2222, authenticated=0),
                            word(0xFFFFFFF00AB48200, 0x3333), 0, 0, 0],
                     placement=placement)

    unauth = tmp / 'unauth.bin'
    unauth.write_bytes(fileset([('com.apple.kernel', kernel),
                                ('com.apple.iokit.IOStorageFamily', unauth_image)]))
    done = run(['--kernelcache', str(unauth), '--vtable', '0xFFFFFFF007A20000',
                '--table', str(table_path), '--require-entry'], tmp)
    case('--require-entry fails on an unauthenticated slot',
         done.returncode == 1 and 'not an authenticated rebase' in done.stdout, done.stdout)

    # 2. a discriminator that does not match is a disagreement
    bad = tmp / 'bad.tsv'
    bad.write_text(table([rows[0], (1, 'external', rows[1][2], 0x9999), rows[2]]))
    done = run(args[:-1] + [str(bad)], tmp)
    case('a different discriminator is reported', '0x9999' in done.stdout, done.stdout)
    case('a disagreement is counted', '1 disagree' in done.stdout, done.stdout)
    done = run(args[:-1] + [str(bad), '--require-match'], tmp)
    case('--require-match fails on a disagreement', done.returncode == 1, done.stdout)

    # 3. a target in a data segment cannot be judged
    data_slot = tmp / 'data.tsv'
    data_slot.write_text(table([(0, 'own', rows[0][2], 0x1111)]))

    def data_image(placement):
        return macho([('__DATA', 0xFFFFFFF007A30000, 0x1000, 0x1000)],
                     filetype=11, words_at=0x1000,
                     words=[0, 0, word(0xFFFFFFF007A30100, 0x1111), 0, 0, 0],
                     placement=placement)

    data_cache = tmp / 'data.bin'
    data_cache.write_bytes(fileset([('com.apple.kernel', kernel),
                                    ('com.apple.iokit.IOStorageFamily', data_image)]))
    done = run(['--kernelcache', str(data_cache), '--vtable', '0xFFFFFFF007A30000',
                '--table', str(data_slot)], tmp)
    case('a data target is undecided', '1 undecided' in done.stdout, done.stdout)
    case('a data target is not called agreement', 'all slots agree' not in done.stdout, done.stdout)

    # 4. the table length is checked
    done = run(args + ['--slots', '4'], tmp)
    case('a table of the wrong length fails',
         done.returncode == 1 and 'expected 4' in done.stdout, done.stdout)

    # 5. the report keeps every slot and never claims hardware
    out = tmp / 'out.json'
    done = run(args + ['--out', str(out)], tmp)
    try:
        result = json.loads(out.read_text())
    except (OSError, ValueError):
        result = {}
    case('the report keeps all slots', len(result.get('findings', [])) == 3)
    case('the report never claims hardware', result.get('hardware_verified') is False)
    case('the report names the vtable', result.get('vtable') == '0xfffffff007a20000')

    # 6. missing inputs fail loudly
    done = run(['--kernelcache', str(tmp / 'nope.bin'), '--vtable', '0x1',
                '--table', str(table_path)], tmp)
    case('a missing kernelcache fails', done.returncode == 1 and 'FAIL' in done.stdout, done.stdout)
    done = run(['--kernelcache', str(cache), '--vtable', '0x1',
                '--table', str(tmp / 'nope.tsv')], tmp)
    case('a missing table fails', done.returncode == 1 and 'FAIL' in done.stdout, done.stdout)

    failed = [name for name, ok, _ in CASES if not ok]
    for name, ok, detail in CASES:
        if not ok:
            print(f'FAIL {name}')
            if detail:
                print(f'     {detail[:400]}')
    if failed:
        print(f'TESTS FAILED {len(failed)} of {len(CASES)} case(s)')
        return 1
    print(f'TESTS OK {len(CASES)} case(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
