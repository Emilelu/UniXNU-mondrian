#!/usr/bin/env python3
"""Self-test for scripts/patch-armcpu-validate.py, on synthetic kernels.

The patch rewrites eight bytes in a signed arm64e function, and every earlier
version of this file got one of those details wrong in a way no build could
report: the return instruction was a plain `ret` under a `pacibsp` prologue
(P-278), and the search stopped one window short of the end of the segment.

So the fixtures here are real Mach-O containers: a parent image with a
__PRELINK_INFO plist naming `com.apple.driver.AppleARMPlatform`, a kext header
at a known file offset, and a __TEXT_EXEC segment holding the prologue and the
tail that follows it. Nothing is stubbed out; the tool is run as it runs in the
payload step, and the bytes it writes are read back and compared.
"""
import importlib.util
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # this file lives in scripts/tests/
PATCHER = ROOT / 'scripts' / 'patch-armcpu-validate.py'

MC_HEADER = 32
LC_SEGMENT_64 = 0x19
MH_EXECUTE, MH_KEXT_BUNDLE = 2, 11
SUBTYPE_ARM64, SUBTYPE_ARM64E, SUBTYPE_FILES = 0, 0x80000002, 0xc0000002

PARENT_TEXT = 0x1000        # parent __TEXT covers the headers and the kext
KEXT_HEADER = 0x400         # kext Mach-O header, inside the parent's __TEXT
TEXT_BYTES = 0x800          # file offset of the kext's __TEXT_EXEC
CODE_BYTES = 0x100          # generous: room for a site anywhere in the window
INFO_AT = 0x1000            # parent __PRELINK_INFO, right after __TEXT
PARENT_VA = 0x100000000

EXPECT = bytes.fromhex('ff8304d1fc6f0ca9')   # sub sp, sp, #0x120 ; stp x28, x27, [sp, #192]
TAIL = bytes.fromhex('fa670da9f85f0ea9')     # stp x26, x25, [sp, #208] ; stp x24, x23, [sp, #224]
PATCH_RETAB = bytes.fromhex('20008052ff0f5fd6')    # mov w0, #1 ; retab
PATCH_RET = bytes.fromhex('20008052c0035fd6')      # mov w0, #1 ; ret
PAC_PREFIX = bytes.fromhex('5f2403d57f2303d5')     # bti c ; pacibsp


def segment(name, va, size, fileoff, filesize):
    body = struct.pack('<II16sQQQQIIII', LC_SEGMENT_64, 72, name.encode(), va, size,
                       fileoff, filesize, 7, 7, 0, 0)
    assert len(body) == 72
    return body


def header(kind, commands, flags=0, subtype=SUBTYPE_ARM64E):
    payload = b''.join(commands)
    return struct.pack('<8I', 0xfeedfacf, 0x0100000c, subtype, kind,
                       len(commands), len(payload), flags, 0) + payload


def plist(load_address, identifier='com.apple.driver.AppleARMPlatform'):
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<plist version="1.0"><dict>'
        b'<key>_PrelinkInfoDictionary</key><array><dict>'
        b'<key>CFBundleIdentifier</key><string>' + identifier.encode() + b'</string>'
        b'<key>_PrelinkExecutableLoadAddr</key><integer>' + hex(load_address).encode() + b'</integer>'
        b'<key>_PrelinkExecutableSize</key><integer>' + hex(0x1000).encode() + b'</integer>'
        b'</dict></array></dict></plist>\n'
    )


def build(code, *, origin='absolute', kext=True, plist_bytes=None,
          subtype=SUBTYPE_ARM64E, entry_prefix=b'', site_at=0x40):
    """A parent MH_EXECUTE holding one kext whose __TEXT_EXEC starts at TEXT_BYTES.

    Every field is written into a buffer that is already the final length: a
    slice assignment of a different length would silently shift the plist, and
    the fixture would then fail for a reason that has nothing to do with the
    tool (which is how the first version of this file looked green on paper and
    parsed an empty blob).
    """
    entries = plist(PARENT_VA + KEXT_HEADER) if kext else plist(
        PARENT_VA + KEXT_HEADER, identifier='com.apple.driver.NotThisBoard')
    if plist_bytes is not None:
        entries = plist_bytes
    body = bytearray(INFO_AT + len(entries))
    parent = header(MH_EXECUTE, [
        segment('__TEXT', PARENT_VA, PARENT_TEXT, 0, PARENT_TEXT),
        segment('__PRELINK_INFO', PARENT_VA + INFO_AT, len(entries), INFO_AT, len(entries)),
    ], subtype=subtype)
    child = header(
        MH_KEXT_BUNDLE,
        [segment('__TEXT_EXEC', PARENT_VA + TEXT_BYTES, len(code),
                 TEXT_BYTES if origin == 'absolute' else TEXT_BYTES - KEXT_HEADER, len(code))],
        subtype=subtype)
    if entry_prefix:
        prefix_at = site_at - len(entry_prefix)
        if prefix_at < 0:
            raise ValueError('entry prefix is outside the synthetic text')
        code = bytearray(code)
        code[prefix_at:site_at] = entry_prefix
        code = bytes(code)
    body[0:len(parent)] = parent
    body[KEXT_HEADER:KEXT_HEADER + len(child)] = child
    body[TEXT_BYTES:TEXT_BYTES + len(code)] = code
    body[INFO_AT:INFO_AT + len(entries)] = entries
    return bytes(body)


def code_with(site_at, window=EXPECT, length=CODE_BYTES):
    code = bytearray(length)
    code[site_at:site_at + 8] = window
    code[site_at + 8:site_at + 16] = TAIL
    return bytes(code)


def run(kernel, *flags):
    done = subprocess.run([sys.executable, str(PATCHER), str(kernel), *flags],
                          capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


class Tests:
    def __init__(self):
        self.failures = []
        self.checks = 0

    def check(self, name, condition, detail=''):
        self.checks += 1
        if not condition:
            self.failures.append(f'{name}{": " + detail if detail else ""}')

    def equal(self, name, actual, expected):
        self.check(name, actual == expected, f'{actual!r} != {expected!r}')


def load_module():
    spec = importlib.util.spec_from_file_location('patch_armcpu_validate', PATCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    tests = Tests()
    module = load_module()

    tests.equal('arm64_replacement', module.PATCH_RET, PATCH_RET)
    tests.equal('arm64e_replacement', module.PATCH_RETAB, PATCH_RETAB)
    tests.equal('ret_encoding', struct.unpack('<I', module.PATCH_RET[4:])[0], 0xD65F03C0)
    tests.equal('retab_encoding', struct.unpack('<I', module.PATCH_RETAB[4:])[0], 0xD65F0FFF)

    tmp = Path(tempfile.mkdtemp(prefix='armcpu-validate-'))
    cases = (
        ('arm64-absolute', 'absolute', SUBTYPE_ARM64, b'', PATCH_RET, 'ret'),
        ('arm64-relative', 'relative', SUBTYPE_ARM64, b'', PATCH_RET, 'ret'),
        ('arm64e-fileset', 'absolute', SUBTYPE_FILES, PAC_PREFIX, PATCH_RETAB, 'retab'),
    )
    for name, origin, subtype, prefix, expected_patch, instruction in cases:
        site = 0x40
        kernel = tmp / f'{name}.macho'
        kernel.write_bytes(build(code_with(site), origin=origin, subtype=subtype,
                                 entry_prefix=prefix, site_at=site))
        rc, out = run(kernel, '--check')
        tests.equal(f'{name}.check_rc', rc, 0)
        tests.check(f'{name}.check_finds_site', 'original bytes match' in out, out.strip())
        tests.check(f'{name}.abi_reported', f'return ABI {instruction}' in out, out.strip())
        tests.check(f'{name}.check_reports_offset', f'file offset {TEXT_BYTES + site:#x}' in out, out.strip())

        before = kernel.read_bytes()
        rc, out = run(kernel, '--apply')
        tests.equal(f'{name}.apply_rc', rc, 0)
        tests.check(f'{name}.apply_instruction', f'mov w0, #1 ; {instruction}' in out, out.strip())
        after = kernel.read_bytes()
        tests.equal(f'{name}.length_kept', len(after), len(before))
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        tests.equal(f'{name}.changed_offsets', changed, list(range(TEXT_BYTES + site, TEXT_BYTES + site + 8)))
        tests.equal(f'{name}.wrote_abi_patch', after[TEXT_BYTES + site:TEXT_BYTES + site + 8], expected_patch)
        tests.equal(f'{name}.tail_untouched', after[TEXT_BYTES + site + 8:TEXT_BYTES + site + 16], TAIL)
        rc, out = run(kernel, '--check')
        tests.equal(f'{name}.idempotent_rc', rc, 0)
        tests.check(f'{name}.idempotent_says_patched', 'already patched' in out, out.strip())
        rc, out = run(kernel, '--apply')
        tests.equal(f'{name}.second_rc', rc, 0)
        tests.equal(f'{name}.second_is_noop', kernel.read_bytes(), after)

    # The window ending at the last aligned 16-byte site must be searched.
    site = CODE_BYTES - 16
    kernel = tmp / 'last.macho'
    kernel.write_bytes(build(code_with(site), subtype=SUBTYPE_ARM64, site_at=site))
    rc, out = run(kernel, '--check')
    tests.equal('last_site.rc', rc, 0)
    tests.check('last_site.found', 'original bytes match' in out, out.strip())
    tests.check('last_site.uses_plain_ret', 'return ABI ret (plain arm64)' in out, out.strip())

    # A previously shipped bad patch must be diagnosed, not accepted as idempotent.
    site = 0x40
    kernel = tmp / 'wrong-pac-return.macho'
    code = bytearray(code_with(site))
    code[site:site + 8] = PATCH_RET
    kernel.write_bytes(build(bytes(code), subtype=SUBTYPE_FILES, entry_prefix=PAC_PREFIX, site_at=site))
    rc, out = run(kernel, '--check')
    tests.check('pac_plain_ret_refused', rc != 0, out.strip())
    tests.check('pac_plain_ret_diagnostic', 'patched for the wrong return ABI' in out and PATCH_RETAB.hex() in out, out.strip())

    # A wrong retab on a non-PAC ARM64 function is also rejected.
    kernel = tmp / 'wrong-arm64-retab.macho'
    code = bytearray(code_with(site))
    code[site:site + 8] = PATCH_RETAB
    kernel.write_bytes(build(bytes(code), subtype=SUBTYPE_ARM64, site_at=site))
    rc, out = run(kernel, '--check')
    tests.check('arm64_retab_refused', rc != 0, out.strip())
    tests.check('arm64_retab_diagnostic', 'patched for the wrong return ABI' in out and PATCH_RET.hex() in out, out.strip())

    # Two sites, no tail, no kext: each is a distinct fault with its own message.
    kernel = tmp / 'twice.macho'
    code = bytearray(code_with(0x40))
    code[0x80:0x88] = EXPECT
    code[0x88:0x90] = TAIL
    kernel.write_bytes(build(bytes(code)))
    rc, out = run(kernel, '--check')
    tests.check('duplicate.refused', rc != 0, out.strip())
    tests.check('duplicate.names_count', 'original=2' in out, out.strip())

    kernel = tmp / 'no-tail.macho'
    code = bytearray(CODE_BYTES)
    code[0x40:0x48] = EXPECT
    kernel.write_bytes(build(bytes(code)))
    rc, out = run(kernel, '--check')
    tests.check('no_tail.refused', rc != 0, out.strip())
    tests.check('no_tail.names_nothing_found', 'no window held it at all' in out, out.strip())

    kernel = tmp / 'no-kext.macho'
    kernel.write_bytes(build(code_with(0x40), kext=False))
    rc, out = run(kernel, '--check')
    tests.check('missing_kext.refused', rc != 0, out.strip())
    tests.check('missing_kext.names_it', 'com.apple.driver.AppleARMPlatform is not in this kernel'
                in out, out.strip())

    print(f'{tests.checks - len(tests.failures)}/{tests.checks} checks passed')
    for failure in tests.failures:
        print(f'FAIL {failure}')
    if tests.failures:
        return 1
    print('OK the patcher selects ret/retab from the function entry and refuses ABI mismatches')
    return 0


if __name__ == '__main__':
    sys.exit(main())