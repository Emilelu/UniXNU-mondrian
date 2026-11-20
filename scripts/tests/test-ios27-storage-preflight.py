#!/usr/bin/env python3
"""Tests for check-ios27-storage-preflight.py.

The fixtures are synthetic filesets: a stripped input kernelcache, and a built
collection that carries the IOStorageFamily entry and a 190-slot vtable.  The
prelink report is bound to both by hash, so a report from an older build is a
failure rather than a pass.
"""

import hashlib
import json
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


def repo(tmp, config_on, include_on=None):
    if include_on is None:
        include_on = config_on
    (tmp / 'configs').mkdir(exist_ok=True)
    include = '["ArmDTPlatform", "ArmCpu", "XnuPrelink", "NativeUfs"]' if include_on \
        else '["ArmDTPlatform", "ArmCpu", "XnuPrelink"]'
    (tmp / 'board.toml').write_text(
        '[os_overrides."ios-27.0.1-24A446".components]\n'
        f'include = {include}\n'
        '[os_overrides."ios-27.0.1-24A446".kernel]\n'
        'defconfig = "mondrian_ios27_defconfig"\n')
    (tmp / 'configs' / 'mondrian_ios27_defconfig').write_text(
        '# fixture\nCONFIG_XNU_NATIVE_UFS=' + ('y' if config_on else 'n') + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_text(cache_hash, candidate_hash, missing=None, layout=None):
    record = {'inputs': {'kernelcache_sha256': cache_hash, 'entry': 'com.apple.kernel'},
              'candidate_sha256': candidate_hash,
              'candidate_written': True,
              'missing': missing or {},
              'stubbed': {},
              'missing_address_space': 'output collection'}
    if layout is not None:
        record['statistics'] = {'segment_layout': layout}
    return json.dumps(record) + '\n'


def run(tmp, extra=()):
    return subprocess.run([sys.executable, str(TOOL), '--root', str(tmp)] + list(extra),
                          capture_output=True, text=True, encoding='utf-8', cwd=tmp)


def main():
    tmp = Path(tempfile.mkdtemp(prefix='storage-preflight-'))
    table_rows = rows()
    table = tmp / 'table.tsv'
    table.write_text(table_text(table_rows))
    short = tmp / 'short.tsv'
    short.write_text(table_text(table_rows[:189]))

    input_cache = tmp / 'input.bin'
    input_cache.write_bytes(fileset([('com.apple.kernel', kernel)]))
    pass_cache = tmp / 'pass.bin'
    pass_cache.write_bytes(fileset([('com.apple.kernel', kernel),
                                    (ENTRY, lambda placement: image(placement, table_rows))]))
    fail_cache = tmp / 'bad-slot.bin'
    fail_cache.write_bytes(fileset([('com.apple.kernel', kernel),
                                    (ENTRY, lambda placement: image(placement, table_rows, 7))]))
    cache_hash, pass_hash, fail_hash = digest(input_cache), digest(pass_cache), digest(fail_cache)

    good = tmp / 'good.json'
    good.write_text(report_text(cache_hash, pass_hash))
    slot_bad = tmp / 'slot-bad.json'
    slot_bad.write_text(report_text(cache_hash, fail_hash))
    untranslated = tmp / 'untranslated.json'
    untranslated.write_text(report_text(
        cache_hash, pass_hash, missing={'bundle': {'0xFFFFFFF00AA00100': 1}},
        layout={'__DATA': {'new': '0xFFFFFFF009000000', 'size': '0x1000'}}))
    stale_cache = tmp / 'stale-cache.json'
    stale_cache.write_text(report_text('0' * 64, pass_hash))
    stale_collection = tmp / 'stale-collection.json'
    stale_collection.write_text(report_text(cache_hash, '1' * 64))

    off = tmp / 'off'
    off.mkdir()
    repo(off, False)
    done = run(off)
    case('switch off with no inputs is pending', done.returncode == 0, done.stdout)
    case('the pending note names the switch', 'NOTE storage: stage 0 does not build NativeUfs' in done.stdout, done.stdout)
    case('the pending run says pending', 'storage preflight: pending' in done.stdout, done.stdout)

    garbage = tmp / 'garbage.bin'
    garbage.write_bytes(b'not a mach-o')
    done = run(off, ['--collection', str(garbage), '--kernelcache', str(garbage),
                     '--report', str(slot_bad)])
    case('switch off stays green with failing inputs', done.returncode == 0, done.stdout)
    case('the failing entry is still reported',
         '[entry] --require-entry on the collection: FAIL' in done.stdout, done.stdout)

    on = tmp / 'on'
    on.mkdir()
    repo(on, True)
    base = ['--vtable', hex(VTABLE), '--table', str(table)]
    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache),
                    '--report', str(good)] + base)
    case('switch on with both checks passing is green', done.returncode == 0, done.stdout)
    case('the passing run says passed', 'storage preflight: passed' in done.stdout, done.stdout)
    case('the slot assertion reads 190 slots', 'slots: 190 read' in done.stdout, done.stdout)
    case('the run names both bindings',
         'binding: collection' in done.stdout and 'binding: kernelcache' in done.stdout, done.stdout)

    done = run(on, ['--collection', str(fail_cache), '--kernelcache', str(input_cache),
                    '--report', str(slot_bad)] + base)
    case('switch on with a slot mismatch is red', done.returncode == 1, done.stdout)
    case('the mismatch is named',
         '[entry] --require-entry on the collection: FAIL' in done.stdout, done.stdout)

    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache),
                    '--report', str(untranslated)] + base)
    case('switch on with an untranslated target is red', done.returncode == 1, done.stdout)
    case('the untranslated target is named', 'untranslated: 1 target' in done.stdout, done.stdout)

    done = run(on, ['--kernelcache', str(input_cache), '--report', str(good)] + base)
    case('switch on without a collection is red', done.returncode == 1, done.stdout)
    case('the missing collection is named', 'no --collection supplied' in done.stdout, done.stdout)

    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache),
                    '--report', str(stale_cache)] + base)
    case('a report from another kernelcache is red', done.returncode == 1, done.stdout)
    case('the stale kernelcache is named',
         'the report was made from kernelcache' in done.stdout, done.stdout)

    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache),
                    '--report', str(stale_collection)] + base)
    case('a report about another collection is red', done.returncode == 1, done.stdout)
    case('the stale collection is named',
         'the report describes collection' in done.stdout, done.stdout)

    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache),
                    '--report', str(good), '--table', str(short), '--vtable', hex(VTABLE)])
    case('a table that is not 190 rows is red', done.returncode == 1, done.stdout)
    case('the row count is named', 'table has 189 rows, expected 190' in done.stdout, done.stdout)

    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache),
                    '--report', str(good), '--table', str(table), '--vtable', hex(VTABLE),
                    '--slots', '189'])
    case('the slot count cannot be lowered from the command line', done.returncode != 0,
         done.stdout + done.stderr)

    done = run(on, ['--collection', str(pass_cache), '--kernelcache', str(input_cache)] + base)
    case('switch on without a report is red', done.returncode == 1, done.stdout)
    case('the missing report is named', 'no --report supplied' in done.stdout, done.stdout)

    half_config = tmp / 'half-config'
    half_config.mkdir()
    repo(half_config, True, False)
    done = run(half_config)
    case('a config that claims the driver without the component is red',
         done.returncode == 1, done.stdout)
    case('the half-set switch is named', 'the selectors disagree' in done.stdout, done.stdout)

    half_include = tmp / 'half-include'
    half_include.mkdir()
    repo(half_include, False, True)
    done = run(half_include)
    case('a component selected without the config is red', done.returncode == 1, done.stdout)

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
