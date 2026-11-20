#!/usr/bin/env python3
"""Tests for check-ios27-prelink-closure.py.

The fixtures are synthetic Mach-O files: a plain kernel, a fileset whose
com.apple.kernel child is stripped, and one whose child names its targets.
The real pinned kernelcache is the stripped case, and that answer decides
whether the 650 sites are a parameter to tune or a property of the input.
"""

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'check-ios27-prelink-closure.py'
CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def macho(segments, symbols=None, filetype=2, size=0x4000):
    """Build a minimal 64-bit Mach-O with segment commands and an optional symtab."""
    commands = b''
    for name, vmaddr, vmsize in segments:
        commands += struct.pack('<II16sQQQQiiII', 0x19, 72, name.encode(),
                                vmaddr, vmsize, 0, size, 7, 5, 0, 0)
    ncmds = len(segments)
    symoff = 0x800
    if symbols:
        symtab = b''
        strings = b'\0'
        for name, value in symbols:
            symtab += struct.pack('<IBBHQ', len(strings), 0x0F, 1, 0, value)
            strings += name.encode() + b'\0'
        stroff = symoff + len(symtab)
        commands += struct.pack('<IIIIII', 0x2, 24, symoff, len(symbols),
                                stroff, len(strings))
        ncmds += 1
    data = bytearray(size)
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, -2147483646,
                         filetype, ncmds, len(commands), 0x00200085, 0)
    data[0:32] = header
    data[32:32 + len(commands)] = commands
    if symbols:
        data[symoff:symoff + len(symtab)] = symtab
        data[stroff:stroff + len(strings)] = strings
    return bytes(data)


def fileset(inner, name='com.apple.kernel', offset=0x1000):
    """Wrap one inner Mach-O in an MH_FILESET with a single LC_FILESET_ENTRY."""
    entry = struct.pack('<IIQQII', 0x80000035, 32 + len(name) + 1, 0,
                        offset, 32, 0) + name.encode() + b'\0'
    entry += b'\0' * ((8 - len(entry) % 8) % 8)
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, -2147483646,
                         12, 1, len(entry), 0x00200085, 0)
    data = bytearray(offset + len(inner))
    data[0:32] = header
    data[32:32 + len(entry)] = entry
    data[offset:offset + len(inner)] = inner
    return bytes(data)


def run(args, tmp):
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, text=True, cwd=tmp)


def main():
    tmp = Path(tempfile.mkdtemp(prefix='closure-'))
    address = 0xfffffff007005000
    segments = [('__TEXT', 0xfffffff007004000, 0x4000),
                ('__PRELINK_TEXT', 0xfffffff004000000, 0)]

    # 1. a stripped kernel cannot name its owner targets
    report = tmp / 'report.json'
    report.write_text(json.dumps({
        'missing': {'com.apple.driver.Test': {hex(address): 3}},
        'stubbed': {'com.apple.driver.Test': {hex(address + 8): 2}},
    }))
    kernel = tmp / 'kernel.bin'
    kernel.write_bytes(macho(segments))
    done = run(['--report', str(report), '--kernelcache', str(kernel)], tmp)
    case('a stripped kernel is accepted as an input', done.returncode == 0, done.stderr)
    case('distinct symbols and references are counted separately',
         '1 symbols, 3 references' in done.stdout, done.stdout)
    case('the stub sites and references are counted',
         '1 sites, 2 references' in done.stdout, done.stdout)
    case('a zero symbol table is printed as zero', 'nsyms 0' in done.stdout, done.stdout)
    case('a stripped kernel gets closure-needs-symbols',
         'closure-needs-symbols' in done.stdout, done.stdout)
    case('the zero-sized prelink segment is shown',
         '__PRELINK_TEXT 0x0' in done.stdout, done.stdout)

    # 2. a fileset child is found by name
    wrapped = tmp / 'cache.bin'
    wrapped.write_bytes(fileset(macho(segments)))
    done = run(['--report', str(report), '--kernelcache', str(wrapped)], tmp)
    case('the fileset child is named in the output',
         'com.apple.kernel filetype 2' in done.stdout, done.stdout)
    case('the fileset verdict is the same',
         'closure-needs-symbols' in done.stdout, done.stdout)

    # 3. a symbol at the target address makes the closure resolvable
    named = tmp / 'named.bin'
    named.write_bytes(macho(segments, symbols=[('_owner_target', address)]))
    done = run(['--report', str(report), '--kernelcache', str(named)], tmp)
    case('a named target is counted as nameable', '1 nameable' in done.stdout, done.stdout)
    case('a named target gets closure-resolvable',
         'closure-resolvable' in done.stdout, done.stdout)

    # 4. a symbol somewhere else does not rescue the target
    elsewhere = tmp / 'elsewhere.bin'
    elsewhere.write_bytes(macho(segments, symbols=[('_other', address + 0x100)]))
    done = run(['--report', str(report), '--kernelcache', str(elsewhere)], tmp)
    case('an unrelated symbol does not make the target nameable',
         '0 nameable' in done.stdout, done.stdout)
    case('an unrelated symbol still needs symbols',
         'closure-needs-symbols' in done.stdout, done.stdout)

    # 5. --require-named turns the verdict into an exit code
    done = run(['--report', str(report), '--kernelcache', str(named),
                '--require-named'], tmp)
    case('--require-named passes when every target is named', done.returncode == 0, done.stdout)
    done = run(['--report', str(report), '--kernelcache', str(kernel),
                '--require-named'], tmp)
    case('--require-named fails when the input is stripped', done.returncode == 1, done.stdout)

    # 6. the report records the two counts separately
    out = tmp / 'out.json'
    done = run(['--report', str(report), '--kernelcache', str(kernel),
                '--out', str(out)], tmp)
    try:
        result = json.loads(out.read_text())
    except (OSError, ValueError):
        result = {}
    case('the JSON keeps symbols and references apart',
         result.get('missing_symbols') == 1 and result.get('missing_references') == 3,
         json.dumps(result)[:200])
    case('the JSON never claims hardware', result.get('hardware_verified') is False)
    case('the JSON names the verdict', result.get('verdict') == 'closure-needs-symbols')

    # 7. missing inputs fail loudly
    done = run(['--report', str(tmp / 'nope.json'), '--kernelcache', str(kernel)], tmp)
    case('a missing report fails', done.returncode == 1 and 'FAIL' in done.stdout, done.stdout)
    done = run(['--report', str(report), '--kernelcache', str(tmp / 'nope.bin')], tmp)
    case('a missing kernelcache fails', done.returncode == 1 and 'FAIL' in done.stdout, done.stdout)

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
