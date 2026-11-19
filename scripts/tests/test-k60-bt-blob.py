#!/usr/bin/env python3
"""Check that k60_bt_blob.s and the NGPUADD2 container it embeds agree.

Why this exists: the .incbin carrier hands the kernel a pointer and a byte
count, and nothing in the C code or the assembler checks that the two describe
the same bytes.  The Metal carrier got exactly this wrong once (P-196: the
length constant omitted the alignment padding between bodies, and the device
rejected the last entry with "body out of range").  Bluetooth is smaller but the
failure shape is identical, so the pair is checked on the host:

  * the length constant equals the container's byte count,
  * the container header's total and record count describe the container,
  * every record lies inside the container, is 8-byte aligned, and the records
    tile it exactly (no gap, no overlap),
  * a build with no firmware emits a zero-length stub instead of a container.

Usage:
    scripts/tests/test-k60-bt-blob.py                     # fixture suite
    scripts/tests/test-k60-bt-blob.py --assembly <file> [--container <file>]
"""
import argparse
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / 'scripts/gen-k60-bt-blob.py'
MAGIC = b'NGPUADD2'
HEADER = 24
ALIGN = 8
MAX_BYTES = 4 * 1024 * 1024
MAX_NAME = 160


def pad(n):
    return (n + ALIGN - 1) & ~(ALIGN - 1)


def parse_container(data):
    """Return (count, total, entries); raise ValueError on anything the kernel rejects.

    Mirrors bsd/dev/qbt_k60.c: k60_addon_find() walks the records from byte 24,
    each record is u32 nameLen, u32 mode, u64 size, u64 packedSize, the name
    padded to 8 and the body padded to 8, and the walk must stay inside the
    container whose header total must equal the byte count.
    """
    if len(data) < HEADER:
        raise ValueError('container is %d bytes, shorter than the %d-byte header'
                         % (len(data), HEADER))
    if data[:8] != MAGIC:
        raise ValueError('container magic is %r, expected %r' % (data[:8], MAGIC))
    count, _reserved, total = struct.unpack_from('<IIQ', data, 8)
    if count == 0:
        raise ValueError('container declares zero records')
    if total != len(data):
        raise ValueError('container header says %d bytes but the file is %d bytes'
                         % (total, len(data)))
    if len(data) > MAX_BYTES:
        raise ValueError('container is %d bytes, over the %d-byte kernel limit'
                         % (len(data), MAX_BYTES))
    entries = []
    off = HEADER
    for index in range(count):
        if off % ALIGN:
            raise ValueError('record %d starts at %d, not %d-byte aligned' % (index, off, ALIGN))
        if off + HEADER > total:
            raise ValueError('record %d starts past the end of the container' % index)
        name_len, _mode, size, packed = struct.unpack_from('<IIQQ', data, off)
        if not 2 <= name_len <= MAX_NAME:
            raise ValueError('record %d name length %d outside 2..%d' % (index, name_len, MAX_NAME))
        name_bytes = pad(name_len)
        data_bytes = pad(packed)
        record = HEADER + name_bytes + data_bytes
        if off + record > total:
            raise ValueError('record %d runs past the end of the container' % index)
        if data[off + HEADER + name_len - 1] != 0:
            raise ValueError('record %d name is not NUL terminated' % index)
        if packed != size:
            raise ValueError('record %d is compressed (%d -> %d) and the kernel has no zlib'
                             % (index, size, packed))
        entries.append((off, size, data[off + HEADER:off + HEADER + name_len - 1].decode()))
        off += record
    if off != total:
        raise ValueError('records end at %d but the container is %d bytes: the last record '
                         'overlaps the header total' % (off, total))
    return count, total, entries


def build_container(records):
    body = b''
    for name, data in records:
        encoded = name.encode() + b'\0'
        body += struct.pack('<IIQQ', len(encoded), 0o644, len(data), len(data))
        body += encoded + bytes(-len(encoded) % ALIGN)
        body += data + bytes(-len(data) % ALIGN)
    return MAGIC + struct.pack('<IIQ', len(records), 0, HEADER + len(body)) + body


def quad_of(text):
    match = re.search(r'^_k60_bt_blob_len:\s*\n\s*\.quad\s+(\d+)\s*$', text, re.M)
    return None if match is None else int(match.group(1))


def check(assembly, container=None):
    """Return the problems in one generated assembly file (empty list is good)."""
    problems = []
    if not assembly.is_file():
        return ['%s: the generated assembly file is missing' % assembly]
    text = assembly.read_text()
    if '_k60_bt_blob:' not in text:
        problems.append('%s: no _k60_bt_blob label' % assembly)
    if not re.search(r'^\.globl\s+_k60_bt_blob_len\s*$', text, re.M):
        problems.append('%s: _k60_bt_blob_len is not exported' % assembly)
    quads = re.findall(r'^_k60_bt_blob_len:\s*\n\s*\.quad\s+(\d+)\s*$', text, re.M)
    incbins = re.findall(r'^\s*\.incbin\s+"([^"]+)"\s*$', text, re.M)
    if len(quads) != 1:
        return problems + ['%s: expected exactly one _k60_bt_blob_len .quad, found %d'
                           % (assembly, len(quads))]
    declared = int(quads[0])
    if len(incbins) > 1:
        return problems + ['%s: %d .incbin directives; the kernel reads one blob'
                           % (assembly, len(incbins))]
    if not incbins:
        if declared != 0:
            problems.append('%s: declares %d bytes but carries no .incbin (empty stub)'
                            % (assembly, declared))
        return problems
    embedded = Path(incbins[0])
    if not embedded.is_absolute():
        embedded = (assembly.parent / embedded).resolve()
    if not embedded.is_file():
        return problems + ['%s: the embedded container is missing' % embedded]
    data = embedded.read_bytes()
    if declared != len(data):
        problems.append('%s: the length constant says %d bytes but the container is %d bytes'
                        % (assembly, declared, len(data)))
    try:
        count, total, entries = parse_container(data)
    except ValueError as error:
        return problems + ['%s: %s' % (embedded, error)]
    if total != declared:
        problems.append('%s: container total %d disagrees with the length constant %d'
                        % (embedded, total, declared))
    if len(entries) != count:
        problems.append('%s: header declares %d records, parsed %d'
                        % (embedded, count, len(entries)))
    if container is not None:
        if not container.is_file():
            problems.append('%s: the expected container is missing' % container)
        else:
            expected = container.read_bytes()
            if hashlib.sha256(expected).hexdigest() != hashlib.sha256(data).hexdigest():
                problems.append('%s: the embedded bytes are not the packed container %s'
                                % (assembly, container))
    return problems


def generate(directory, container):
    assembly = directory / 'k60_bt_blob.s'
    command = [sys.executable, str(GENERATOR), '--assembly', '--output', str(assembly)]
    if container is not None:
        command += ['--container', str(container)]
    done = subprocess.run(command, capture_output=True, text=True)
    return assembly, done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assembly', type=Path,
                        help='a real generated file to check instead of the fixtures')
    parser.add_argument('--container', type=Path,
                        help='the container the build passed to the generator')
    args = parser.parse_args()

    if args.assembly is not None:
        problems = check(args.assembly, args.container)
        if problems:
            for problem in problems:
                print('  - ' + problem)
            print('\u274c %s: the bluetooth container is inconsistent' % args.assembly)
            return 1
        print('\u2705 %s: container table is self-consistent' % args.assembly)
        return 0

    cases = []
    with tempfile.TemporaryDirectory() as name:
        work = Path(name)

        def fixture(tag, records, expectation=None):
            container = work / (tag + '.bin')
            container.write_bytes(build_container(records))
            assembly, done = generate(work, container)
            if done.returncode != 0:
                cases.append((tag + ': the generator refused a good container',
                              'generator stderr: ' + done.stderr.strip()))
                return
            problems = check(assembly, container)
            if expectation is None:
                cases.append((tag, '\n'.join(problems)))
            else:
                matched = [p for p in problems if expectation in p]
                cases.append((tag, '' if matched else
                              'no problem matched %r; got %r' % (expectation, problems)))

        fixture('healthy container', [('qca/hpbtfw20.tlv', b'X' * 40),
                                      ('qca/hpnv20.bin', b'Y' * 24),
                                      ('qca/hpbtfw21.tlv', b'Z' * 8)])

        # A stub is what a build with no firmware must produce.
        stub, done = generate(work, None)
        cases.append(('empty stub', '' if check(stub) == [] else str(check(stub))))
        # ... and a stub that claims bytes it does not carry must be rejected.
        broken = work / 'stub-lying.s'
        broken.write_text(stub.read_text().replace('.quad 0', '.quad 4096'))
        cases.append(('stub that claims bytes',
                      '' if any('carries no .incbin' in p for p in check(broken))
                      else str(check(broken))))

        def broken_container(tag, mutate, expectation, declared=None):
            good = build_container([('qca/hpbtfw20.tlv', b'A' * 32),
                                    ('qca/hpnv20.bin', b'B' * 16)])
            container = work / (tag + '.bin')
            container.write_bytes(mutate(good))
            assembly = work / (tag + '.s')
            assembly.write_text('.section __DATA,__const\n'
                                '.globl _k60_bt_blob\n'
                                '_k60_bt_blob:\n'
                                '    .incbin "%s"\n'
                                '.globl _k60_bt_blob_len\n'
                                '_k60_bt_blob_len:\n'
                                '    .quad %d\n'
                                % (container, len(good) if declared is None else declared))
            problems = check(assembly, container)
            cases.append((tag, '' if any(expectation in p for p in problems)
                          else 'no problem matched %r; got %r' % (expectation, problems)))

        broken_container('length constant disagrees',
                         lambda blob: blob, 'length constant', declared=4096)
        broken_container('magic is not NGPUADD2',
                         lambda blob: b'X' * 8 + blob[8:], 'magic')
        broken_container('header total disagrees',
                         lambda blob: blob[:16] + struct.pack('<Q', len(blob) + 8) + blob[24:],
                         'header says')
        broken_container('record runs past the end',
                         lambda blob: blob[:24] + struct.pack('<IIQQ', 12, 0o644, 4096, 4096)
                         + blob[48:], 'runs past the end')
        broken_container('records do not tile the container',
                         lambda blob: blob[:16] + struct.pack('<Q', len(blob) + 8) + blob[24:]
                         + b'\0' * 8, 'records end at')
        broken_container('zero records',
                         lambda blob: blob[:8] + struct.pack('<IIQ', 0, 0, len(blob)) + blob[24:],
                         'zero records')

    failures = [(name, detail) for name, detail in cases if detail]
    for name, detail in cases:
        print(('FAIL ' if detail else 'PASS ') + name + ('' if not detail else '\n  ' + detail))
    print('TESTS OK %d cases (%d failure(s))' % (len(cases), len(failures)))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
