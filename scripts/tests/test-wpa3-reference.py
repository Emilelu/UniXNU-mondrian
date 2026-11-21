#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host-only WPA3 reference gate: compile the t970 vectors and station simulator.

The implementation under test is the clean-room t970 WPA3 library, not this
repository. This test refuses a missing reference, a compiler failure, or any
output other than the two exact success lines. It never builds a kernel, a
payload or a station archive; it is the executable form of
docs/research/wifi/WPA3-PORT-PLAN.md section 4.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

VECTOR_LINE = 'ALL wpa3_test CHECKS PASSED'
SIM_LINE = 'ALL sta_sim_wpa3 SCENARIOS PASSED'


def reference_root(cli: str | None) -> pathlib.Path | None:
    if cli:
        path = pathlib.Path(cli)
        return path if path.is_dir() else None
    candidates = [
        os.environ.get('K60_T970'),
        '/mnt/e/hackios/UniXNU-t970',
        'E:/hackios/UniXNU-t970',
    ]
    for item in candidates:
        if item and pathlib.Path(item).is_dir():
            return pathlib.Path(item)
    return None


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_and_run(clang: str, root: pathlib.Path, test: str, out: pathlib.Path) -> tuple[int | None, str, str]:
    source = root / 'drivers/T970Wifi/T970WifiWpa3.c'
    header = root / 'drivers/T970Wifi/T970WifiWpa3.h'
    test_source = root / 'drivers/T970Wifi/tests' / test
    for path in (source, header, test_source):
        if not path.is_file():
            return None, '', 'reference file is missing: %s' % path
    compile_cmd = [
        clang, '-std=c11', '-O1', '-I', str(source.parent),
        str(source), str(test_source), '-o', str(out),
    ]
    try:
        compiled = subprocess.run(compile_cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return None, '', 'compiler is missing: %s' % clang
    if compiled.returncode != 0:
        return 1, compiled.stdout, compiled.stderr
    try:
        ran = subprocess.run([str(out)], capture_output=True, text=True)
    except FileNotFoundError:
        return None, '', 'compiled test is missing: %s' % out
    return ran.returncode, ran.stdout, ran.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--t970', help='t970 checkout (default: K60_T970, then /mnt/e and E:/)')
    parser.add_argument('--clang', default=shutil.which('clang') or '', help='host C compiler')
    args = parser.parse_args(argv)

    if args.t970 and not pathlib.Path(args.t970).is_dir():
        print('FAIL reference: %s is not a directory' % args.t970, file=sys.stderr)
        return 2
    root = reference_root(args.t970)
    if root is None:
        print('FAIL reference: no t970 checkout; pass --t970', file=sys.stderr)
        return 2
    if not args.clang or not (pathlib.Path(args.clang).is_file() or shutil.which(args.clang)):
        print('FAIL compiler: %s is not executable; pass --clang' % (args.clang or 'clang'), file=sys.stderr)
        return 2

    source = root / 'drivers/T970Wifi/T970WifiWpa3.c'
    header = root / 'drivers/T970Wifi/T970WifiWpa3.h'
    for required in (source, header, root / 'drivers/T970Wifi/tests/wpa3_test.c',
                     root / 'drivers/T970Wifi/tests/sta_sim_wpa3.c'):
        if not required.is_file():
            print('FAIL reference: %s is missing' % required, file=sys.stderr)
            return 2
    print('reference t970: %s' % root)
    print('reference sha256: c=%s h=%s' % (sha256(source), sha256(header)))
    print('compiler: %s' % args.clang)

    failures = 0
    with tempfile.TemporaryDirectory(prefix='k60-wpa3-') as tmp:
        for test, expected in (('wpa3_test.c', VECTOR_LINE),
                               ('sta_sim_wpa3.c', SIM_LINE)):
            out = pathlib.Path(tmp) / test.replace('.c', '')
            rc, stdout, stderr = build_and_run(args.clang, root, test, out)
            if rc is None:
                print('FAIL reference: %s' % stderr.strip(), file=sys.stderr)
                return 2
            if rc != 0:
                print('FAIL compile/run %s: rc=%d' % (test, rc), file=sys.stderr)
                print((stdout + stderr).strip(), file=sys.stderr)
                failures += 1
            elif expected not in stdout:
                print('FAIL output %s: expected exactly %r' % (test, expected), file=sys.stderr)
                print(stdout.strip(), file=sys.stderr)
                failures += 1
            else:
                print('PASS %s: %s' % (test, expected))

    if failures:
        print('FAIL wpa3 reference: %d of 2 checks failed' % failures, file=sys.stderr)
        return 1
    print('2/2 wpa3 reference checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
