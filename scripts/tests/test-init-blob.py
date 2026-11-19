#!/usr/bin/env python3
"""Verify the embedded-init patch keeps its promises (F2, P-194).

The wallpaper fix has to change three things in one patch file: the 52 KB init
Mach-O, the 14 KB PONGJOB1 varpack that carries pong/etc/var.skel, and the
two hunk headers that count their lines.  A silent mismatch there does not
fail the build -- it fails on the phone as a truncated blob.  Each case below
recomputes the claim from the patch bytes instead of trusting the generator.

Run: python3 scripts/tests/test-init-blob.py
"""
from __future__ import annotations

import importlib.util
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches' / 'xnu' / '0401-k60-embedded-init.patch'

CASES = 0
FAILURES = 0


def check(condition, label, detail=''):
    global CASES, FAILURES
    CASES += 1
    if condition:
        print(f'ok   {label}')
    else:
        FAILURES += 1
        print(f'FAIL {label}' + (f': {detail}' if detail else ''))


def load_build():
    spec = importlib.util.spec_from_file_location('k60_build', ROOT / 'userland' / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared(text, define):
    return int(re.search(r'\+#define ' + define + r' (\d+)', text).group(1))


def hunk_claims(text):
    """Return [(header_line_no, declared_count, actual_plus_lines)] for new files."""
    out = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        m = re.match(r'@@ -0,0 \+1,(\d+) @@$', line)
        if not m:
            continue
        stop = next((i for i in range(index + 1, len(lines))
                     if lines[i].startswith(('--- a/', 'diff --git'))), len(lines))
        actual = sum(1 for value in lines[index + 1:stop]
                     if value.startswith('+') and not value.startswith('+++'))
        out.append((index + 1, int(m.group(1)), actual))
    return out


def main():
    build = load_build()
    text = PATCH.read_text(encoding='utf-8')

    init = build.embedded_blob(text, 'bsd/kern/k60_init_blob.h')
    varpack = build.embedded_blob(text, 'bsd/kern/k60_varpack_blob.h')
    jobs = build.embedded_blob(text, 'bsd/kern/k60_bootjobs_blob.h')

    check(len(init) == declared(text, 'K60_INIT_BLOB_LEN'), 'init length matches K60_INIT_BLOB_LEN',
          f'{len(init)} vs {declared(text, "K60_INIT_BLOB_LEN")}')
    check(len(varpack) == declared(text, 'K60_VARPACK_LEN'), 'varpack length matches K60_VARPACK_LEN',
          f'{len(varpack)} vs {declared(text, "K60_VARPACK_LEN")}')
    check(len(jobs) == declared(text, 'K60_BOOTJOBS_LEN'), 'boot-jobs length matches K60_BOOTJOBS_LEN')

    records = build.split_boot_jobs(varpack)
    check(build.join_boot_jobs(records) == varpack, 'varpack split/join round-trips byte for byte')
    check(len(records) == struct.unpack_from('<I', varpack, 8)[0], 'varpack record count agrees with header')

    skeletons = [r for r in records if r['name'] == b'pong/etc/var.skel']
    check(len(skeletons) == 1, 'varpack carries exactly one pong/etc/var.skel', str(len(skeletons)))
    if skeletons:
        rows = skeletons[0]['data'].decode().splitlines()
        wallpaper = [row for row in rows
                     if row.startswith('d\t') and row.rsplit('\t', 1)[-1] in (
                         '/private/var/pong/stock-wallpaper', '/private/var/pong/Wallpaper')]
        check(len(wallpaper) == 2, 'var.skel seeds both wallpaper view directories', str(wallpaper))
        check(all(row.split('\t')[1:4] == ['755', '0', '0'] for row in wallpaper),
              'wallpaper view directories are 0755 root:root', str(wallpaper))

    # Mutating one array must leave every hunk header counting its own lines.
    probe = text
    payload = bytes(range(256)) * 3
    probe = build.replace_embedded_array(probe, 'bsd/kern/k60_varpack_blob.h', 'K60_VARPACK_LEN',
                                         '+static const unsigned char k60_varpack_blob[K60_VARPACK_LEN] = {',
                                         payload)
    probe = build.replace_embedded_array(probe, 'bsd/kern/k60_init_blob.h', 'K60_INIT_BLOB_LEN',
                                         '+static const unsigned char k60_init_blob[K60_INIT_BLOB_LEN] = {',
                                         payload)
    for line_no, claim, actual in hunk_claims(probe):
        check(claim == actual, f'hunk at line {line_no} counts its lines', f'{claim} vs {actual}')
    check(build.embedded_blob(probe, 'bsd/kern/k60_varpack_blob.h') == payload,
          'varpack payload survives a rewrite')
    check(build.embedded_blob(probe, 'bsd/kern/k60_init_blob.h') == payload,
          'init payload survives a rewrite')

    check(init[:4] == b'\xcf\xfa\xed\xfe', 'init blob is a thin 64-bit Mach-O')
    check(struct.unpack_from('<I', init, 12)[0] == 2, 'init blob is MH_EXECUTE')
    check(struct.unpack_from('<I', init, 16)[0] == 15, 'init blob keeps the booted ncmds=15 layout')

    print(f'TESTS OK {CASES} cases ({FAILURES} failure(s))')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
