#!/usr/bin/env python3
"""Fixtures for scripts/k60-fileset-stamp.py.

The tool edits four bytes inside a prelinked collection, so the fixtures are the
same shape as the artifact checker's: a real outer header, real 32-byte
LC_FILESET_ENTRY commands whose entry_id points at the name, and real child
headers at the offsets those commands give. Nothing is stubbed, because a
stubbed fileset would accept a wrong entry_id and never notice.

Each case removes or changes exactly one property the loader checks, so a pass
here means the tool refuses everything except the one edit it is for: the label
on `com.apple.kernel`, never a code byte, never another child.
"""
import importlib.util
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / 'scripts' / 'k60-fileset-stamp.py'

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
MH_EXECUTE, MH_FILESET = 2, 12
MH_DYLIB_IN_CACHE = 0x80000000
LC_FILESET_ENTRY = 0x80000035
OUTER = 0xc0000002
USER = 0x80000002


def collection(outer=OUTER, kernel_subtype=USER, kernel_flags=0x80200001, kernel_type=MH_EXECUTE,
               children=3, duplicate_kernel=False):
    """Outer header, N entry commands, then N child headers laid out after them."""
    names = []
    for index in range(children):
        names.append(b'com.apple.kernel' if index == 0 or duplicate_kernel
                     else ('com.apple.kext%d' % index).encode())
    entries_size = 32 * children
    commands_at = 32
    names_at = commands_at + entries_size
    child_at = names_at + sum(len(name) + 1 for name in names)
    child_at = (child_at + 15) & ~15

    blobs = []
    offset = names_at
    for index, name in enumerate(names):
        # entry_id is relative to the start of this load command, not to the first one.
        blobs.append(struct.pack('<IIQQII', LC_FILESET_ENTRY, 32, 0,
                                 child_at + 32 * index,
                                 offset - (commands_at + 32 * index), 0))
        offset += len(name) + 1
    commands = b''.join(blobs)
    name_blob = b''.join(name + b'\0' for name in names)
    outer_header = struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64, outer, MH_FILESET,
                               children, entries_size, 0, 0)

    children_blob = b''
    for index in range(children):
        first = index == 0 or duplicate_kernel
        children_blob += struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64,
                                     kernel_subtype if first else OUTER,
                                     kernel_type if first else MH_EXECUTE,
                                     0, 0, kernel_flags if first else 0x80200001, 0)

    data = outer_header + commands + name_blob
    data += b'\0' * (child_at - len(data))
    return bytearray(data + children_blob), child_at


class Tests:
    def __init__(self):
        self.checks = 0
        self.failures = []

    def check(self, name, condition, detail=''):
        self.checks += 1
        if not condition:
            self.failures.append(f'{name}{": " + detail if detail else ""}')

    def equal(self, name, actual, expected):
        self.check(name, actual == expected, f'{actual!r} != {expected!r}')

    def refuses(self, name, needle, blob, apply=False):
        try:
            MODULE.stamp(blob, apply=apply)
        except MODULE.Failure as error:
            self.check(name, needle in str(error), f'{needle!r} not in {error!r}')
            return
        self.check(name, False, 'no refusal')


def load():
    spec = importlib.util.spec_from_file_location('k60_fileset_stamp', STAMP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = None


def main():
    global MODULE
    tests = Tests()
    module = MODULE = load()

    # The exact shape of our round-17d output: every child right but one label.
    blob, child_at = collection()
    offset, old, new, applied = module.stamp(blob, apply=True)
    tests.equal('stamp.offset', offset, child_at + 8)
    tests.equal('stamp.values', (old, new), (USER, OUTER))
    tests.check('stamp.wrote', applied)
    tests.equal('stamp.new_bytes', struct.unpack_from('<I', blob, child_at + 8)[0], OUTER)

    # Idempotent: a second run on its own output must not fail (P-278's lesson).
    offset2, old2, new2, applied2 = module.stamp(blob, apply=True)
    tests.equal('stamp.idempotent_values', (old2, new2), (OUTER, OUTER))
    tests.check('stamp.idempotent_no_write', not applied2)

    # Nothing else may move: only the top byte of the label differs (0x80 -> 0xc0),
    # measured against a fresh unstamped copy.
    fresh, _ = collection()
    changed = [i for i in range(len(blob)) if fresh[i] != blob[i]]
    tests.equal('stamp.only_one_byte', (len(changed), changed[0] if changed else None),
                (1, child_at + 11))

    # The other children keep their own label, whatever it was.
    tests.equal('stamp.other_children_untouched',
                struct.unpack_from('<I', blob, child_at + 32 + 8)[0], OUTER)

    # A report-only run says what it would do and leaves the file alone.
    quiet, _ = collection()
    offset3, _, _, applied3 = module.stamp(quiet, apply=False)
    tests.check('stamp.report_does_not_write', not applied3)
    tests.equal('stamp.report_leaves_bytes',
                struct.unpack_from('<I', quiet, offset3)[0], USER)

    # Every other property of the member rule is refused rather than invented.
    plain, _ = collection()
    struct.pack_into('<I', plain, 12, MH_EXECUTE)
    tests.refuses('refuse.not_a_collection', 'nothing to stamp', plain)
    tests.refuses('refuse.child_not_execute', 'not MH_EXECUTE',
                  collection(kernel_type=MH_FILESET)[0])
    tests.refuses('refuse.child_without_dylib_in_cache', 'lacks MH_DYLIB_IN_CACHE',
                  collection(kernel_flags=0x00200001)[0])
    tests.refuses('refuse.duplicate_kernel', 'appears 3 times',
                  collection(duplicate_kernel=True)[0])
    tests.refuses('refuse.missing_kernel', 'no com.apple.kernel',
                  collection(children=2)[0].replace(b'com.apple.kernel', b'com.apple.kextX'))
    tests.refuses('refuse.truncated', 'run past the end', collection()[0][:40])

    # The CLI end: report, apply, then a clean second apply.
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / 'kernel.macho'
        data, child_at = collection()
        path.write_bytes(bytes(data))
        before = path.stat().st_size
        report = subprocess.run([sys.executable, str(STAMP), str(path)],
                                capture_output=True, text=True)
        tests.equal('cli.report_rc', report.returncode, 0)
        tests.check('cli.report_says_apply', 'use --apply' in report.stdout, report.stdout)
        tests.equal('cli.report_size_unchanged', path.stat().st_size, before)
        applied = subprocess.run([sys.executable, str(STAMP), str(path), '--apply'],
                                 capture_output=True, text=True)
        tests.equal('cli.apply_rc', applied.returncode, 0)
        tests.check('cli.apply_reports_offset', 'at file offset' in applied.stdout, applied.stdout)
        again = subprocess.run([sys.executable, str(STAMP), str(path), '--apply'],
                               capture_output=True, text=True)
        tests.equal('cli.again_rc', again.returncode, 0)
        tests.check('cli.again_says_already', 'already carries' in again.stdout, again.stdout)
        broken = Path(scratch) / 'broken.macho'
        broken.write_bytes(b'not a mach-o' * 8)
        failed = subprocess.run([sys.executable, str(STAMP), str(broken)],
                                capture_output=True, text=True)
        tests.equal('cli.broken_rc', failed.returncode, 1)
        tests.check('cli.broken_message', 'not a 64-bit little-endian Mach-O' in failed.stdout,
                    failed.stdout)

    print(f'{tests.checks - len(tests.failures)}/{tests.checks} checks passed')
    for failure in tests.failures:
        print(f'FAIL {failure}')
    if tests.failures:
        return 1
    print('OK the stamp fixes one label and refuses every other member-rule defect')
    return 0


if __name__ == '__main__':
    sys.exit(main())
