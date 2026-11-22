#!/usr/bin/env python3
"""Tests for check-kprintf-enabled.py (P-308).

The gate must reject a 27 board whose kernel_args lack -enable_kprintf_spam, and
accept one that has it.  It must not judge a 16 profile (different build type,
different rule set).
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import textwrap

CHECK = pathlib.Path(__file__).resolve().parents[1] / 'check-kprintf-enabled.py'

BASE = '''
[board]
os_profile = "{profile}"

[payload]
kernel_args = [{args}]
'''

OVERRIDE = '''
[board]
os_profile = "ios-27.0.1-24A446"

[payload]
kernel_args = ["-v", "debug=0x14e"]

[os_overrides."ios-27.0.1-24A446".payload]
kernel_args = [{args}]
'''

failures: list[str] = []


def run(board: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        pathlib.Path(tmp, 'board.toml').write_text(textwrap.dedent(board), encoding='utf-8')
        return subprocess.run([sys.executable, str(CHECK), '--device', tmp],
                              capture_output=True, text=True)


def check(name: str, process: subprocess.CompletedProcess, want: int) -> None:
    if process.returncode != want:
        failures.append(f'{name}: rc={process.returncode} want={want} out={process.stdout}{process.stderr}')


check('27 with the flag', run(BASE.format(profile='ios-27.0.1-24A446',
                                          args='"-v", "-enable_kprintf_spam"')), 0)
check('27 without the flag', run(BASE.format(profile='ios-27.0.1-24A446',
                                             args='"-v", "debug=0x14e"')), 1)
check('27 override supplies the flag', run(OVERRIDE.format(args='"-v", "-enable_kprintf_spam"')), 0)
check('27 override drops the flag', run(OVERRIDE.format(args='"-v", "debug=0x14e"')), 1)
check('16 profile is skipped', run(BASE.format(profile='ipados-16.6.1-20G81', args='"-v"')), 0)

if failures:
    for failure in failures:
        print('FAIL ' + failure)
    sys.exit(1)
print('TESTS OK 5 cases')
