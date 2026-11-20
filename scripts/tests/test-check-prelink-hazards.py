#!/usr/bin/env python3
"""The prelink hazard gate must fail on an outside slot and pass on covered ones."""

import importlib.util
import json
import pathlib
import struct
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / 'scripts/check-prelink-hazards.py'

spec = importlib.util.spec_from_file_location('hazards', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CHECKS = 0
FAILED = 0
CPU = 0x100000c
SUBTYPE = 0xc0000002 - 2 ** 32


def ok(name, condition, detail=''):
    global CHECKS, FAILED
    CHECKS += 1
    if condition:
        return
    FAILED += 1
    print(f'FAIL {name}' + (f': {detail}' if detail else ''))


def segment_command(address, size, fileoff):
    body = struct.pack('<16sQQQQiiII', b'__TEXT', address, size, fileoff, size,
                       5, 5, 0, 0)
    return struct.pack('<II', module.SEGMENT_CMD, 8 + len(body)) + body


def header(filetype, ncmds, sizeofcmds, subtype=SUBTYPE):
    blob = bytearray(32)
    struct.pack_into('<IiiIIII', blob, 0, module.MH_MAGIC_64, CPU, subtype,
                     filetype, ncmds, sizeofcmds, 0)
    return bytes(blob)


def collection(address=0x100000000, size=0x1000):
    """One segment plus one entry whose fileoff points at a real child header."""
    segment = segment_command(address, size, 0)
    name = b'com.apple.kernel\0'
    entry_size = 32
    child_at = 32 + len(segment) + entry_size + len(name)
    child_segment = segment_command(address + 0x100, 0x100, child_at + 32)
    child = header(2, 1, len(child_segment)) + child_segment
    entry = struct.pack('<IIQQI', module.FILESET_ENTRY_CMD, entry_size,
                        address + 0x100, child_at, 0)
    return (header(module.MH_FILESET, 2, len(segment) + entry_size)
            + segment + entry + name + child)


def board(kernel, missing):
    directory = pathlib.Path(tempfile.mkdtemp())
    (directory / 'kernel').mkdir()
    (directory / 'kernel/kernel.macho').write_bytes(kernel)
    (directory / 'kernel/kernel.json').write_text(json.dumps({'missing': missing}),
                                                  encoding='utf-8')
    return directory


def allowlist(text=None):
    path = pathlib.Path(tempfile.mkdtemp()) / 'allow.toml'
    path.write_text(text if text is not None else 'schema_version = 1\n', encoding='utf-8')
    module.ALLOWLIST = path
    return path


def main():
    image = collection()

    allowlist()
    covered = board(image, {'b': {'0x100000100': 1}})
    rc = module.main([str(covered)])
    ok('pass.covered_address', rc == 0, f'rc={rc}')

    allowlist()
    outside = board(image, {'b': {'0x200000000': 1}})
    rc = module.main([str(outside)])
    ok('fail.outside_without_review', rc == 1, f'rc={rc}')

    allowlist('[[slot]]\nbundle="b"\naddress="0x200000000"\n'
              'reason="checked against the reference"\nreview="lead, 2026-11-21"\n')
    reviewed = board(image, {'b': {'0x200000000': 1}})
    rc = module.main([str(reviewed)])
    ok('pass.reviewed_slot', rc == 0, f'rc={rc}')

    path = allowlist('[[slot]]\nbundle="b"\naddress="0x200000000"\nreason="x"\n')
    try:
        module.reviewed(path)
    except module.Failure as error:
        ok('fail.slot_without_reviewer', 'review' in str(error), str(error))
    else:
        ok('fail.slot_without_reviewer', False, 'accepted a slot with no reviewer')

    module.ALLOWLIST = pathlib.Path(tempfile.mkdtemp()) / 'absent.toml'
    try:
        module.main([str(covered)])
    except module.Failure as error:
        ok('fail.missing_allowlist', 'still has to exist' in str(error), str(error))
    else:
        ok('fail.missing_allowlist', False, 'accepted a missing allowlist')

    print(f'{CHECKS - FAILED}/{CHECKS} checks passed')
    if FAILED:
        return 1
    print('OK the hazard gate separates outside-segment slots from covered ones')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
