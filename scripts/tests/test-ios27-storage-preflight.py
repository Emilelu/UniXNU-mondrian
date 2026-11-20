#!/usr/bin/env python3
"""Tests for check-ios27-storage-preflight.py.

The fixtures are synthetic filesets with a 190-slot storage vtable and a
com.apple.kernel entry.  The preflight drives the two real checkers, so the
fixtures only have to be structurally honest: absolute segment offsets in the
outer collection and the table tail present.
"""

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'check-ios27-storage-preflight.py'
CASES = []
BASE = 0xFFFFFFF007004000
ENTRY = 'com.apple.iokit.IOStorageFamily'
OWN = 0xFFFFFFF007A10100
EXTERNAL = 0xFFFFFFF00AB48100
VTABLE = 0xFFFFFFF007A20000


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def macho(segments, filetype=2, size=0x4000, words_at=None, words=(), placement=0):
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
    return (authenticated << 63) | (diversity << 32) | ((address - BASE) & 0x3FFFFFFF)


def rows(count=190):
    return [(slot, 'own' if slot % 2 == 0 else 'external', f'method{slot}', 0x1000 + slot)
            for slot in range(count)]


def words(table_rows, bad_slot=None):
    out = [0, 0]
    for slot, kind, _, diversity in table_rows:
        target = OWN if kind == 'own' else EXTERNAL
        div = 0xDEAD if slot == bad_slot else diversity
        out.append(word(target, div))
    out += [0, 0, 0]
    return out


def table_text(table_rows):
    out = 'slot\tkind\tmethod\tsource_diversity\n'
    for slot, kind, method, diversity in table_rows:
        out += f'{slot}\t{kind}\t{method}\t{diversity:#x}\n'
    return out


def image(placement, table_rows, bad_slot=None):
    return macho([('__TEXT', 0xFFFFFFF007A00000, 0x1000, 0),
                  ('__TEXT_EXEC', 0xFFFFFFF007A10000, 0x1000, 0),
                  ('__DATA_CONST', VTABLE, 0x1000, 0x1000)],
                 filetype=11, words_at=0x1000,
                 words=words(table_rows, bad_slot), placement=placement)


def kernel(placement):
    return macho([('__TEXT', 0xFFFFFFF00AA00000, 0x1000, 0),
                  ('__TEXT_EXEC', 0xFFFFFFF00AB48000, 0x1000, 0x1000)],
                 placement=placement)


def repo(tmp, switch_on):
    (tmp / 'configs').mkdir(exist_ok=True)
    include = '["ArmDTPlatform", "ArmCpu", "XnuPrelink", "NativeUfs"]' if switch_on \
        else '["ArmDTPlatform", "ArmCpu", "XnuPrelink"]'
    (tmp / 'board.toml').write_text(
        '[os_overrides."ios-27.0.1-24A446".components]\n'
        f'include = {include}\n'
        '[os_overrides."ios-27.0.1-24A446".kernel]\n'
        'defconfig = "mondrian_ios27_defconfig"\n')
    (tmp / 'configs' / 'mondrian_ios27_defconfig').write_text(
        '# fixture\nCONFIG_XNU_NATIVE_UFS=' + ('y' if switch_on else 'n') + '\n')


def good_report():
    return '{"missing": {}, "stubbed": {}, "missing_address_space": "output collection"}\n'


def bad_report():
    return ('{"missing": {"bundle": {"0xFFFFFFF00AA00100": 1}}, "stubbed": {}, '
            '"statistics": {"segment_layout": {"__DATA": '
            '{"new": "0xFFFFFFF009000000", "size": "0x1000"}}}, '
            '"missing_address_space": "output collection"}\n')


def run(tmp, extra=()):
    return subprocess.run([sys.executable, str(TOOL), '--root', str(tmp)] + list(extra),
                          capture_output=True, text=True, encoding='utf-8', cwd=tmp)


def main():
    tmp = Path(tempfile.mkdtemp(prefix='storage-preflight-'))
    table_rows = rows()
    table = tmp / 'table.tsv'
    table.write_text(table_text(table_rows))
    pass_cache = tmp / 'pass.bin'
    pass_cache.write_bytes(fileset([('com.apple.kernel', kernel),
                                    (ENTRY, lambda placement: image(placement, table_rows))]))
    fail_cache = tmp / 'bad.bin'
    fail_cache.write_bytes(fileset([('com.apple.kernel', kernel),
                                    (ENTRY, lambda placement: image(placement, table_rows, 7))]))
    good = tmp / 'good.json'
    good.write_text(good_report())
    bad = tmp / 'bad.json'
    bad.write_text(bad_report())

    off = tmp / 'off'
    off.mkdir()
    repo(off, False)
    done = run(off)
    case('switch off with no inputs is pending', done.returncode == 0, done.stdout)
    case('the pending note names the switch', 'NOTE storage: stage 0 does not build NativeUfs' in done.stdout, done.stdout)
    case('the pending run says pending', 'storage preflight: pending' in done.stdout, done.stdout)

    garbage = tmp / 'garbage.bin'
    garbage.write_bytes(b'not a mach-o')
    done = run(off, ['--kernelcache', str(garbage), '--report', str(bad)])
    case('switch off stays green with failing inputs', done.returncode == 0, done.stdout)
    case('the failing entry is still reported', '[entry] --require-entry: FAIL' in done.stdout, done.stdout)

    on = tmp / 'on'
    on.mkdir()
    repo(on, True)
    done = run(on, ['--kernelcache', str(pass_cache), '--report', str(good),
                    '--vtable', hex(VTABLE), '--table', str(table)])
    case('switch on with both checks passing is green', done.returncode == 0, done.stdout)
    case('the passing run says passed', 'storage preflight: passed' in done.stdout, done.stdout)

    done = run(on, ['--kernelcache', str(fail_cache), '--report', str(good),
                    '--vtable', hex(VTABLE), '--table', str(table)])
    case('switch on with a slot mismatch is red', done.returncode == 1, done.stdout)
    case('the mismatch is named', '[entry] --require-entry: FAIL' in done.stdout, done.stdout)

    done = run(on, ['--kernelcache', str(pass_cache), '--report', str(bad),
                    '--vtable', hex(VTABLE), '--table', str(table)])
    case('switch on with an untranslated target is red', done.returncode == 1, done.stdout)
    case('the untranslated target is named', 'untranslated: 1 target' in done.stdout, done.stdout)

    failed = [name for name, ok, _ in CASES if not ok]
    for name, ok, detail in CASES:
        print(('ok   ' if ok else 'FAIL ') + name)
        if not ok and detail:
            print('     ' + detail.replace('\n', '\n     ')[:1200])
    print(f'TESTS OK {len(CASES) - len(failed)} case(s)' if not failed
          else f'TESTS FAILED {len(failed)} case(s)')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
